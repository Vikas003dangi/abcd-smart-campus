import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


@database_sync_to_async
def save_chat_message(user_id, chat_type, session_id, content, reply_to_id=None, client_msg_id=None):
    try:
        from django.contrib.auth.models import User
        from users.models import Message, ChatSession, DirectChatSession, GroupChatSession, GroupMessage, GuidyBlock
        from django.utils.timezone import localtime
        from users.utils import get_user_display_name, get_profile_photo_url, clean_guidy_message_content, strip_html_for_notification

        user = User.objects.filter(id=user_id).first()
        content = clean_guidy_message_content(content)
        if not user or not content:
            return {'error': 'User or content missing'}

        reply_to_obj = None
        recipients = []
        if chat_type == 'group':
            group = GroupChatSession.objects.filter(id=session_id).first()
            if not group or not group.is_active or getattr(group, 'deleted_at', None):
                return {'error': 'Group is inactive or deleted'}
            is_member = (user in group.members.all() or group.created_by_id == user.id or user.is_staff or user.is_superuser)
            if not is_member:
                return {'error': 'You are not a member of this group'}
            if reply_to_id:
                reply_to_obj = GroupMessage.objects.filter(id=reply_to_id, group=group).first()
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
                return {'error': 'Direct chat is inactive or ended'}
            is_participant = (direct_session.user1_id == user.id or direct_session.user2_id == user.id or user.is_staff or user.is_superuser)
            if not is_participant:
                return {'error': 'Forbidden'}
            other = direct_session.user2 if direct_session.user1_id == user.id else direct_session.user1
            if other:
                if GuidyBlock.objects.filter(blocker=other, blocked=user).exists():
                    return {'error': 'You are blocked by this user.'}
                if GuidyBlock.objects.filter(blocker=user, blocked=other).exists():
                    return {'error': 'You have blocked this user. Unblock them to chat.'}
                recipients = [other]
            if reply_to_id:
                reply_to_obj = Message.objects.filter(id=reply_to_id, direct_session=direct_session).first()
            msg = Message.objects.create(
                direct_session=direct_session,
                sender=user,
                content=content,
                message_type='text',
                reply_to=reply_to_obj
            )
        else:  # guidance / session
            session = ChatSession.objects.filter(id=session_id).first()
            if not session or not session.is_active:
                return {'error': 'Guidance session is inactive or ended'}
            if getattr(session, 'request', None):
                is_participant = (
                    session.request.student_id == user.id or
                    (session.request.alumni and session.request.alumni.user_id == user.id) or
                    user.is_staff or user.is_superuser
                )
                other = session.request.alumni.user if (session.request.alumni and session.request.student_id == user.id) else session.request.student
            else:
                is_participant = (session.user_one_id == user.id or session.user_two_id == user.id or user.is_staff or user.is_superuser)
                other = session.user_two if session.user_one_id == user.id else session.user_one
            if not is_participant:
                return {'error': 'Forbidden'}
            if other:
                if GuidyBlock.objects.filter(blocker=other, blocked=user).exists():
                    return {'error': 'You are blocked by this user.'}
                if GuidyBlock.objects.filter(blocker=user, blocked=other).exists():
                    return {'error': 'You have blocked this user. Unblock them to chat.'}
                recipients = [other]
            if reply_to_id:
                reply_to_obj = Message.objects.filter(id=reply_to_id, session=session).first()
            msg = Message.objects.create(
                session=session,
                sender=user,
                content=content,
                message_type='text',
                reply_to=reply_to_obj
            )

        reply_preview = None
        if reply_to_obj:
            reply_preview = {
                'id': reply_to_obj.id,
                'content': reply_to_obj.content[:80] if reply_to_obj.content else '',
                'sender': get_user_display_name(reply_to_obj.sender),
                'type': getattr(reply_to_obj, 'message_type', 'text'),
            }

        # Initial delivery check: if recipient is currently online, mark delivered immediately
        try:
            from django.core.cache import cache
            for r in recipients:
                if r and cache.get(f"guidy_presence_{r.id}"):
                    msg.is_delivered = True
                    msg.save(update_fields=['is_delivered'])
                    break
        except Exception:
            pass

        # Trigger background web push and database notifications to recipient(s)
        try:
            import threading
            from django.db import close_old_connections
            from users.notifications import send_push
            from users.models import Notification

            def _notify_bg(recipients_list, sender, message_obj, c_type, s_id):
                close_old_connections()
                delivered_marked = False
                try:
                    sender_name = get_user_display_name(sender)
                    push_title = "Guidy Assistant"
                    clean_msg_content = strip_html_for_notification(message_obj.content)
                    if c_type == 'group':
                        grp = GroupChatSession.objects.filter(id=s_id).first()
                        grp_name = grp.name if (grp and grp.name) else "Group"
                        msg_text = clean_msg_content[:80] if clean_msg_content else "Sent a message"
                        push_body = f"[{grp_name}] {sender_name}: {msg_text}"
                        push_icon = (grp.photo.url if grp and grp.photo else None) or get_profile_photo_url(sender) or "/static/data/favicon/web-app-manifest-192x192.png"
                        push_tag = f"guidy-group-{s_id}"
                        push_url = f"/guidy/?group={s_id}"
                    else:
                        msg_text = clean_msg_content[:80] if clean_msg_content else "Sent a message"
                        push_body = f"{sender_name}: {msg_text}"
                        push_icon = get_profile_photo_url(sender) or "/static/data/favicon/web-app-manifest-192x192.png"
                        push_tag = f"guidy-{c_type}-{s_id}"
                        push_url = f"/guidy/?{c_type}={s_id}"

                    for r in recipients_list:
                        try:
                            from django.core.cache import cache
                            # If recipient currently has this exact chat open live, do not spam push or DB unread notifications
                            active_in_chat = cache.get(f"guidy_active_chat_{r.id}")
                            is_reading_live = (active_in_chat == f"{c_type}_{s_id}")
                        except Exception:
                            is_reading_live = False

                        try:
                            from django.core.cache import cache
                            cache.delete(f"guidy_badge_count_{r.id}")
                            from users.views import get_guidy_badge_count
                            new_badge_val = get_guidy_badge_count(r)
                        except Exception:
                            new_badge_val = 1

                        push_delivered = False
                        if not is_reading_live:
                            try:
                                notif = Notification.objects.filter(user=r, category='guidy', is_read=False).first()
                                if notif:
                                    notif.title = 'Guidy Assistant'
                                    notif.message = push_body[:80]
                                    notif.link = push_url
                                    notif.save()
                                else:
                                    Notification.objects.create(
                                        user=r,
                                        category='guidy',
                                        is_read=False,
                                        title='Guidy Assistant',
                                        message=push_body[:80],
                                        link=push_url
                                    )
                            except Exception:
                                pass

                            try:
                                push_delivered = bool(send_push(
                                    user=r,
                                    title=push_title,
                                    body=push_body,
                                    url=push_url,
                                    icon=push_icon,
                                    badge="/static/data/favicon/favicon-96x96.png",
                                    sound="/static/audio/receive.mp3",
                                    badge_count=new_badge_val,
                                    tag=push_tag,
                                    category="guidy",
                                    source="guidy"
                                ))
                            except Exception:
                                push_delivered = False

                        try:
                            from django.core.cache import cache
                            recipient_online = bool(cache.get(f"guidy_presence_{r.id}") or is_reading_live)
                        except Exception:
                            recipient_online = False

                        # If push reached recipient or recipient is active/online, mark delivered
                        if (push_delivered or recipient_online) and not getattr(message_obj, 'is_delivered', False):
                            try:
                                message_obj.is_delivered = True
                                message_obj.save(update_fields=['is_delivered'])
                                delivered_marked = True
                            except Exception:
                                pass

                        try:
                            from django.core.cache import cache
                            cache.delete(f"guidy_badge_count_{r.id}")
                            from users.views import get_guidy_badge_count
                            new_badge_val = get_guidy_badge_count(r)
                            from asgiref.sync import async_to_sync
                            from channels.layers import get_channel_layer
                            c_layer = get_channel_layer()
                            if c_layer:
                                async_to_sync(c_layer.group_send)(
                                    f"user_{r.id}",
                                    {
                                        "type": "guidy_badge_update",
                                        "guidy_badge_count": new_badge_val,
                                    }
                                )
                        except Exception:
                            pass

                    # Real-time tick upgrade from single check to double check
                    if delivered_marked:
                        try:
                            from asgiref.sync import async_to_sync
                            from channels.layers import get_channel_layer
                            c_layer = get_channel_layer()
                            if c_layer:
                                d_payload = {
                                    "type": "messages_delivered_broadcast",
                                    "chat_type": c_type,
                                    "session_id": s_id,
                                    "message_ids": [message_obj.id],
                                }
                                async_to_sync(c_layer.group_send)(f"guidy_{c_type}_{s_id}", d_payload)
                                async_to_sync(c_layer.group_send)(f"user_{sender.id}", d_payload)
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
            'client_msg_id': client_msg_id,
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
            'is_delivered': bool(getattr(msg, 'is_delivered', False)),
            'is_read': False,
            'is_verified': (user.is_staff or user.is_superuser),
            'recipient_ids': [r.id for r in recipients if r],
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to save Guidy WebSocket chat message: %s", e)
        return {'error': f'Failed to save message: {str(e)}'}


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
                GroupMessage.objects.filter(id__in=read_ids).update(is_delivered=True)
        elif chat_type == 'direct':
            direct_session = DirectChatSession.objects.filter(id=session_id).first()
            if direct_session:
                qs = Message.objects.filter(direct_session=direct_session, is_read=False).exclude(sender=user)
                read_ids = list(qs.values_list('id', flat=True))
                qs.update(is_read=True, is_delivered=True)
        else:  # guidance
            session = ChatSession.objects.filter(id=session_id).first()
            if session:
                qs = Message.objects.filter(session=session, is_read=False).exclude(sender=user)
                read_ids = list(qs.values_list('id', flat=True))
                qs.update(is_read=True, is_delivered=True)

        return read_ids
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to mark Guidy messages read: %s", e)
        return []


@database_sync_to_async
def mark_all_undelivered_for_user(user_id):
    try:
        from django.db.models import Q
        from users.models import Message
        undelivered = list(Message.objects.filter(
            is_delivered=False
        ).filter(
            Q(direct_session__user1_id=user_id) |
            Q(direct_session__user2_id=user_id) |
            Q(session__user_one_id=user_id) |
            Q(session__user_two_id=user_id) |
            Q(session__request__student_id=user_id) |
            Q(session__request__alumni__user_id=user_id)
        ).exclude(sender_id=user_id))

        if not undelivered:
            return {}

        delivered_by_sender = {}
        msg_ids = []
        for m in undelivered:
            msg_ids.append(m.id)
            delivered_by_sender.setdefault(m.sender_id, []).append(m.id)

        Message.objects.filter(id__in=msg_ids).update(is_delivered=True)
        return delivered_by_sender
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("mark_all_undelivered_for_user error: %s", e)
        return {}


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

    @database_sync_to_async
    def update_active_chat(self):
        try:
            from django.core.cache import cache
            if self.user and self.user.is_authenticated:
                cache.set(f"guidy_active_chat_{self.user.id}", f"{self.chat_type}_{self.session_id}", timeout=45)
        except Exception:
            pass

    @database_sync_to_async
    def clear_active_chat(self):
        try:
            from django.core.cache import cache
            if self.user and self.user.is_authenticated:
                current = cache.get(f"guidy_active_chat_{self.user.id}")
                if current == f"{self.chat_type}_{self.session_id}":
                    cache.delete(f"guidy_active_chat_{self.user.id}")
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

        # Keep presence cache and active chat cache alive
        await self.update_user_presence(True)
        await self.update_active_chat()

        # Mark all pending messages sent to this user as delivered, and notify senders
        try:
            delivered_map = await mark_all_undelivered_for_user(self.user.id)
            if delivered_map:
                for s_id, m_ids in delivered_map.items():
                    d_evt = {
                        "type": "messages_delivered_broadcast",
                        "chat_type": self.chat_type,
                        "session_id": self.session_id,
                        "message_ids": m_ids,
                    }
                    await self.channel_layer.group_send(f"user_{s_id}", d_evt)
                    await self.channel_layer.group_send(self.room_group_name, d_evt)
        except Exception:
            pass

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
        # Clear active chat state from cache
        await self.clear_active_chat()

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
            await self.update_active_chat()
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
            client_msg_id = data.get("client_msg_id")
            if not content:
                return

            res = await save_chat_message(
                self.user.id, self.chat_type, self.session_id, content, reply_to_id, client_msg_id
            )
            if isinstance(res, dict) and 'error' in res:
                await self.send(text_data=json.dumps({
                    "type": "chat_message_error",
                    "client_msg_id": client_msg_id,
                    "error": res['error'],
                }))
                return

            if res and isinstance(res, dict):
                # 1. Send to current chat room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message_broadcast",
                        "sender_id": self.user.id,
                        "message": res,
                    }
                )
                # 2. Also send real-time sidebar alert to each recipient's user channel
                for r_id in res.get('recipient_ids', []):
                    await self.channel_layer.group_send(
                        f"user_{r_id}",
                        {
                            "type": "guidy_sidebar_update",
                            "chat_type": self.chat_type,
                            "session_id": int(self.session_id),
                            "sender_id": self.user.id,
                            "sender_name": self.user.get_full_name() or self.user.username,
                            "message": res,
                        }
                    )
            else:
                await self.send(text_data=json.dumps({
                    "type": "chat_message_error",
                    "client_msg_id": client_msg_id,
                    "error": "Failed to save message.",
                }))

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

    async def messages_delivered_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "messages_delivered",
            "chat_type": event.get("chat_type"),
            "session_id": event.get("session_id"),
            "message_ids": event.get("message_ids", []),
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

    async def guidy_badge_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "guidy_badge_update",
            "guidy_badge_count": event.get("guidy_badge_count", 0),
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

        if self.user.is_staff or self.user.is_superuser:
            self.staff_group = "staff_group"
            await self.channel_layer.group_add(self.staff_group, self.channel_name)
            await self.channel_layer.group_add("teachers", self.channel_name)

        await self.accept()

        await self.update_user_presence(True)

        # Mark all pending messages sent to this user as delivered, and notify senders
        try:
            delivered_map = await mark_all_undelivered_for_user(self.user.id)
            if delivered_map:
                for s_id, m_ids in delivered_map.items():
                    await self.channel_layer.group_send(
                        f"user_{s_id}",
                        {
                            "type": "messages_delivered_broadcast",
                            "message_ids": m_ids,
                        }
                    )
        except Exception:
            pass

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'broadcast_group'):
            await self.channel_layer.group_discard(self.broadcast_group, self.channel_name)
        if hasattr(self, 'staff_group'):
            await self.channel_layer.group_discard(self.staff_group, self.channel_name)
            await self.channel_layer.group_discard("teachers", self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get("type") in ["heartbeat", "ping"]:
                await self.update_user_presence(True)
                await self.send(text_data=json.dumps({"type": "heartbeat_ack"}))
            elif data.get("type") == "chat_message":
                await self.send(text_data=json.dumps({
                    "type": "chat_message_error",
                    "client_msg_id": data.get("client_msg_id"),
                    "error": "Notification socket cannot receive chat messages.",
                }))
        except Exception:
            pass

    async def notification(self, event):
        notif_obj = event.get("notification") or {
            "title": event.get("title", ""),
            "message": event.get("message", ""),
            "link": event.get("link", "/"),
            "category": event.get("category", "general"),
        }
        await self.send(text_data=json.dumps({
            "type": "notification",
            "notification": notif_obj,
            "title": notif_obj.get("title", ""),
            "message": notif_obj.get("message", ""),
            "link": notif_obj.get("link", "/"),
        }))

    async def send_notification(self, event):
        notif_obj = event.get("notification") or {
            "title": event.get("title", ""),
            "message": event.get("message", ""),
            "link": event.get("link", "/"),
            "category": event.get("category", "general"),
        }
        await self.send(text_data=json.dumps({
            "type": "notification",
            "notification": notif_obj,
            "title": notif_obj.get("title", ""),
            "message": notif_obj.get("message", ""),
            "link": notif_obj.get("link", "/"),
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

    async def guidy_badge_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "guidy_badge_update",
            "guidy_badge_count": event.get("guidy_badge_count", 0),
        }))

    async def dashboard_stats_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "dashboard_stats_update",
            "stats": event.get("stats", {}),
        }))

    async def messages_delivered_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "messages_delivered",
            "chat_type": event.get("chat_type"),
            "session_id": event.get("session_id"),
            "message_ids": event.get("message_ids", []),
        }))

    async def messages_read_broadcast(self, event):
        await self.send(text_data=json.dumps({
            "type": "messages_read",
            "reader_id": event.get("reader_id"),
            "message_ids": event.get("message_ids", []),
        }))

