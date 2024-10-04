import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils.timesince import timesince

from .templatetags.chatextras import initials
from .models import Room, Message
from account.models import User


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'
        self.user = self.scope['user']
        
        # Join room group
        await self.get_room()
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        if self.user.is_staff:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'users_update'
            })
        
    
    async def disconnect(self, close_code):
        # Leave room 
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        
        if not self.user.is_staff:
            await self.set_room_closed()


    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        _type = text_data_json['type']
        name, message = text_data_json['name'], text_data_json['message']
        agent = text_data_json.get('agent', '')
                
        if _type == 'message':
            new_message = await self.create_message(name, agent, message)
            
            await self.channel_layer.group_send(
                # send message to the group / room
                self.room_group_name, {
                    'type': 'chat_message',
                    'name': name,
                    'message': message,
                    'agent': agent,
                    'initials': initials(name),
                    'created_at': timesince(new_message.created_at),
                }
            )
        elif _type == 'update':
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'writing_active',
                'message': message,
                'name': name,
                'initials': initials(name),
                'agent': agent,
            })
            
            
    
    async def users_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'users_update'
        }))

    
    async def chat_message(self, event):
        # send message to the web socket    
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'name': event['name'],
            'message': event['message'],
            'agent': event['agent'],
            'initials': event['initials'],
            'created_at': event['created_at'],
        }))
    
    
    
    async def writing_active(self, event):
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'message': event['message'], 
            'name': event['name'],
            'agent': event['agent'],
            'initials': event['initials'],
        }))
        
        
    
    @sync_to_async
    def get_room(self):
        self.room = Room.objects.get(uuid=self.room_name)


    @sync_to_async
    def set_room_closed(self):
        self.room = Room.objects.get(uuid=self.room_name)
        self.room.status = Room.CLOSED
        self.room.save()

    
    @sync_to_async
    def create_message(self, sent_by, agent, message):
        message = Message.objects.create(body=message, sent_by=sent_by)

        if agent:
            message.created_by = User.objects.get(pk=agent)
            message.save()

        self.room.messages.add(message)
        return message
        