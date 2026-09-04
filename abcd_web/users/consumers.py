import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


@database_sync_to_async
def save_chat_message(user_id, chat_type, session_id, content, reply_to_id=None):
    try:
        from django.contrib.auth.models import User
        from users.models import Message, ChatSession, DirectChatSession, GroupChatSession, GroupMessage
        from django.utils.timezone import localtime
        from users.utils import get_user_display_name, get_profile_photo_url

        user = User.objects.filter(id=user_id).first()
        if not user or not content:
            return None

        reply_to_obj = None
        if reply_to_id:
            reply_to_obj = Message.objects.filter(id=reply_to_id).first() or GroupMessage.objects.filter(id=reply_to_id).first()

        recipients = []
        if chat_type == 'group':
            group = GroupChatSession.objects.filter(id=session_id).first()
            if not group or not group.is_active:
                return None
            msg = GroupMessage.objects.create(
                group=group,
                sender=user,
                content=content,
                message_type='text',
                reply_to=reply_to_obj
            )
            msg.read_by.add(user)
            recipients = list(group.members.exclude(id=user.id))
        elif chat_type == 'direct':
            direct_session = DirectChatSession.objects.filter(id=session_id).first()
            if not direct_session or not direct_session.is_active:
                return None
            msg = Message.objects.create(
                direct_session=direct_session,
                sender=user,
                content=content,
                message_type='text',
                reply_to=reply_to_obj
            )
            other = direct_session.user2 if direct_session.user1 == user else direct_session.user1
            if other:
                recipients = [other]
        else:  # guidance
            session = ChatSession.objects.filter(id=session_id).first()
            if not session or not session.is_active:
                return None
            msg = Message.objects.create(
                session=session,
                sender=user,
                content=content,
                message_type='text',
                reply_to=reply_to_obj
            )
            if hasattr(session, 'request') and session.request:
                other = session.request.alumni.user if session.request.student == user else session.request.student
            else:
                other = session.user_two if session.user_one == user else session.user_one
            if other:
                recipients = [other]

        reply_preview = None
        if reply_to_obj:
            reply_preview = {
                'id': reply_to_obj.id,
                'content': reply_to_obj.content[:80] if reply_to_obj.content else '',
                'sender': get_user_display_name(reply_to_obj.sender),
                'type': getattr(reply_to_obj, 'message_type', 'text'),
            }

        # Trigger background web push and database notifications to recipient(s)
        try:
            import threading
            from django.db import close_old_connections
            from users.notifications import send_push
            from users.models import Notification

            def _notify_bg(recipients_list, sender, message_obj, c_type, s_id):
                close_old_connections()
                try:
                    sender_name = get_user_display_name(sender)
                    if c_type == 'group':
                        grp = GroupChatSession.objects.filter(id=s_id).first()
                        push_title = grp.name if (grp and grp.name) else sender_name
                        msg_text = message_obj.content[:80] if message_obj.content else "Sent a message"
                        push_body = f"{sender_name}: {msg_text}"
                        push_icon = (grp.photo.url if grp and grp.photo else None) or get_profile_photo_url(sender) or "/static/data/favicon/web-app-manifest-192x192.png"
                        push_tag = f"guidy-group-{s_id}"
                        push_url = f"/guidy/?group={s_id}"
                    else:
                        push_title = sender_name
                        push_body = message_obj.content[:80] if message_obj.content else "Sent a message"
                        push_icon = get_profile_photo_url(sender) or "/static/data/favicon/web-app-manifest-192x192.png"
                        push_tag = f"guidy-{c_type}-{s_id}"
                        push_url = f"/guidy/?{c_type}={s_id}"

                    for r in recipients_list:
                        try:
                            notif = Notification.objects.filter(user=r, category='guidy', is_read=False).first()
                            if notif:
                                notif.title = '💬 New Guidy Message'
                                notif.message = f'{sender_name}: {push_body[:60]}'
                                notif.link = push_url
                                notif.save()
                            else:
                                Notification.objects.create(
                                    user=r,
                                    category='guidy',
                                    is_read=False,
                                    title='💬 New Guidy Message',
                                    message=f'{sender_name}: {push_body[:60]}' if c_type == 'group' else f'New message from {sender_name}',
                                    link=push_url
                                )
                        except Exception:
                            pass

                        try:
                            send_push(
                                user=r,
                                title=push_title,
                                body=push_body,
                                url=push_url,
                                icon=push_icon,
                                badge="/static/data/favicon/favicon-96x96.png",
                                tag=push_tag
                            )
                        except Exception:
                            pass
                finally:
                    close_old_connections()

            threading.Thread(
                target=_notify_bg,
                args=(recipients, user, msg, chat_type, session_id),
                daemon=True
            ).start()
        except Exception:
            pass

        return {
            'id': msg.id,
            'content': msg.content,
            'message_type': msg.message_type,
            'file_url': None,
            'file_name': None,
            'timestamp': localtime(msg.timestamp).strftime('%H:%M'),
            'date': localtime(msg.timestamp).strftime('%Y-%m-%d'),
            'sender_id': user.id,
            'sender_name': get_user_display_name(user),
            'sender_photo': get_profile_photo_url(user),
            'reply_to': reply_preview,
            'is_pinned': False,
            'media_expired': False,
            'is_verified': (user.is_staff or user.is_superuser),
            'recipient_ids': [r.id for r in recipients],
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to save Guidy WebSocket chat message: %s", e)
        return None


@database_sync_to_async
def mark_messages_as_read(user_id, chat_type, session_id):
    try:
        from django.contrib.auth.models import User
        from users.models import Message, DirectChatSession, ChatSession, GroupChatSession, GroupMessage

        user = User.objects.filter(id=user_id).first()
        if not user:
            return []

        read_ids = []
        if chat_type == 'group':
            group = GroupChatSession.objects.filter(id=session_id).first()
            if group:
                msgs = GroupMessage.objects.filter(group=group).exclude(read_by=user)
                for msg in msgs:
                    msg.read_by.add(user)
                    read_ids.append(msg.id)
        elif chat_type == 'direct':
            direct_session = DirectChatSession.objects.filter(id=session_id).first()
            if direct_session:
                qs = Message.objects.filter(direct_session=direct_session, is_read=False).exclude(sender=user)
                read_ids = list(qs.values_list('id', flat=True))
                qs.update(is_read=True)
        else:  # guidance
            session = ChatSession.objects.filter(id=session_id).first()
            if session:
                qs = Message.objects.filter(session=session, is_read=False).exclude(sender=user)
                read_ids = list(qs.values_list('id', flat=True))
                qs.update(is_read=True)

        return read_ids
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to mark Guidy messages read: %s", e)
        return []


@database_sync_to_async
def delete_chat_message(user_id, chat_type, message_id):
    try:
        from users.models import Message, GroupMessage
        if chat_type == 'group':
            msg = GroupMessage.objects.filter(id=message_id, sender_id=user_id).first()
        else:
            msg = Message.objects.filter(id=message_id, sender_id=user_id).first()

        if msg:
            msg.is_deleted = True
            msg.save(update_fields=['is_deleted'])
            return msg.id
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to delete Guidy message: %s", e)
        return None


class GuidyChatConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def update_user_presence(self, is_online):
        try:
            from django.core.cache import cache
            if self.user and self.user.is_authenticated:
                if is_online:
                    cache.set(f"guidy_presence_{self.user.id}", True, timeout=35)
                else:
                    cache.delete(f"guidy_presence_{self.user.id}")
        except Exception:
            pass

    async def connect(self):
        self.chat_type = self.scope['url_route']['kwargs']['chat_type']
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f"guidy_{self.chat_type}_{self.session_id}"
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.user_group = f"user_{self.user.id}"

        # Join room channel group & user's personal group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        # Keep presence cache alive
        await self.update_user_presence(True)

        # Broadcast online presence to room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_presence",
                "user_id": self.user.id,
                "status": "online",
            }
        )

    async def disconnect(self, close_code):
        # Broadcast offline presence to room
        if hasattr(self, 'room_group_name') and hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_presence",
                    "user_id": self.user.id,
                    "status": "offline",
                }
            )
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        if hasattr(self, 'user_group') and hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            return

        event_type = data.get("type")

        if event_type in ["heartbeat", "ping"]:
            await self.update_user_presence(True)
            await self.send(text_data=json.dumps({"type": "heartbeat_ack"}))
            return

        elif event_type == "typing_indicator":
            is_typing = bool(data.get("is_typing", False))
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_typing",
                    "sender_id": self.user.id,
                    "sender_name": self.user.get_full_name() or self.user.username,
                    "is_typing": is_typing,
                }
            )

        elif event_type == "chat_message":
            content = data.get("content", "").strip()
            reply_to_id = data.get("reply_to_id")
            if not content:
                return

            msg_data = await save_chat_message(
                self.user.id, self.chat_type, self.session_id, content, reply_to_id
            )
            if msg_data:
                # 1. Send to current chat room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message_broadcast",
                        "sender_id": self.user.id,
                        "message": msg_data,
                    }
                )
                # 2. Also send real-time sidebar alert to each recipient's user channel
                for r_id in msg_data.get('recipient_ids', []):
                    await self.channel_layer.group_send(
                        f"user_{r_id}",
                        {
                            "type": "guidy_sidebar_update",
                            "chat_type": self.chat_type,
                            "session_id": int(self.session_id),
                            "sender_id": self.user.id,
                            "sender_name": self.user.get_full_name() or self.user.username,
                            "message": msg_data,
                        }
                    )

        elif event_type == "mark_read":
            read_ids = await mark_messages_as_read(self.user.id, self.chat_type, self.session_id)
            if read_ids:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "messages_read_broadcast",
                        "reader_id": self.user.id,
                        "message_ids": read_ids,
                    }
                )

        elif event_type == "delete_message":
            msg_id = data.get("message_id")
            if msg_id:
                deleted_id = await delete_chat_message(self.user.id, self.chat_type, msg_id)
                if deleted_id:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "message_deleted_broadcast",
                            "message_id": deleted_id,
                            "user_id": self.user.id,
                        }
                    )

    async def user_presence(self, event):
        if event["user_id"] != self.user.id:
            await self.send(text_data=json.dumps({
                "type": "user_presence",
                "user_id": event["user_id"],
                "status": event["status"],
            }))

    async def user_typing(self, event):
        if event["sender_id"] != self.user.id:
            await self.send(text_data=json.dumps({
                "type": "typing_indicator",
                "sender_id": event["sender_id"],
                "sender_name": event["sender_name"],
                "is_typing": event["is_typing"],
            }))

    async def chat_message_broadcast(self, event):
        msg_payload = dict(event["message"])
        msg_payload["is_mine"] = (event["sender_id"] == self.user.id)
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "sender_id": event["sender_id"],
            "message": msg_payload,
        }))

    async def guidy_sidebar_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "guidy_sidebar_update",
            "chat_type": event["chat_type"],
            "session_id": event["session_id"],
            "sender_id": event["sender_id"],
            "sender_name": event.get("sender_name", ""),
            "message": event["message"],
        }))

    async def messages_read_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "messages_read",
            "reader_id": event["reader_id"],
            "message_ids": event["message_ids"],
        }))

    async def message_deleted_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_deleted",
            "message_id": event["message_id"],
            "user_id": event["user_id"],
        }))

    async def session_status_changed(self, event):
        await self.send(text_data=json.dumps({
            "type": "session_status_changed",
            "is_active": event.get("is_active", True),
            "ended_by_id": event.get("ended_by_id"),
            "ended_by_name": event.get("ended_by_name", ""),
            "locked_days_left": event.get("locked_days_left", 5),
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def update_user_presence(self, is_online):
        try:
            from django.core.cache import cache
            if self.user and self.user.is_authenticated:
                if is_online:
                    cache.set(f"guidy_presence_{self.user.id}", True, timeout=35)
                else:
                    cache.delete(f"guidy_presence_{self.user.id}")
        except Exception:
            pass

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.user_group = f"user_{self.user.id}"
        self.broadcast_group = "broadcast_all"

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.broadcast_group, self.channel_name)
        await self.accept()

        await self.update_user_presence(True)

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'broadcast_group'):
            await self.channel_layer.group_discard(self.broadcast_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get("type") in ["heartbeat", "ping"]:
                await self.update_user_presence(True)
                await self.send(text_data=json.dumps({"type": "heartbeat_ack"}))
        except Exception:
            pass

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            "type": "notification",
            "notification": event["notification"]
        }))

    async def send_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "broadcast",
            "broadcast": event["broadcast"]
        }))

    async def guidy_sidebar_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "guidy_sidebar_update",
            "chat_type": event["chat_type"],
            "session_id": event["session_id"],
            "sender_id": event["sender_id"],
            "sender_name": event.get("sender_name", ""),
            "message": event["message"],
        }))
