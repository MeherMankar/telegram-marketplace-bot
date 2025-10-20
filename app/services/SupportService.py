import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class TicketStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SupportService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.faq_data = self._load_faq_data()
    
    async def create_ticket(self, user_id: int, subject: str, description: str, 
                          category: str = "general", priority: str = "medium") -> Dict[str, Any]:
        """Create a new support ticket"""
        try:
            ticket = {
                'user_id': user_id,
                'subject': subject,
                'description': description,
                'category': category,
                'priority': priority,
                'status': TicketStatus.OPEN.value,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'messages': [
                    {
                        'sender_id': user_id,
                        'sender_type': 'user',
                        'message': description,
                        'timestamp': datetime.utcnow()
                    }
                ],
                'assigned_to': None,
                'resolution': None
            }
            
            result = await self.db.support_tickets.insert_one(ticket)
            ticket_id = str(result.inserted_id)
            
            # Auto-assign based on category
            await self._auto_assign_ticket(ticket_id, category)
            
            return {
                'success': True,
                'ticket_id': ticket_id,
                'status': TicketStatus.OPEN.value,
                'estimated_response_time': self._get_response_time(priority)
            }
            
        except Exception as e:
            logger.error(f"Error creating support ticket: {e}")
            return {'success': False, 'error': str(e)}
    
    async def add_message_to_ticket(self, ticket_id: str, sender_id: int, 
                                  message: str, sender_type: str = "user") -> Dict[str, Any]:
        """Add a message to an existing ticket"""
        try:
            new_message = {
                'sender_id': sender_id,
                'sender_type': sender_type,
                'message': message,
                'timestamp': datetime.utcnow()
            }
            
            await self.db.support_tickets.update_one(
                {'_id': ticket_id},
                {
                    '$push': {'messages': new_message},
                    '$set': {
                        'updated_at': datetime.utcnow(),
                        'status': TicketStatus.IN_PROGRESS.value if sender_type == 'admin' else TicketStatus.OPEN.value
                    }
                }
            )
            
            return {'success': True, 'message_added': True}
            
        except Exception as e:
            logger.error(f"Error adding message to ticket: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_tickets(self, user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all tickets for a user"""
        try:
            query = {'user_id': user_id}
            if status:
                query['status'] = status
            
            tickets = await self.db.support_tickets.find(query).sort('created_at', -1).to_list(None)
            
            # Format tickets for display
            formatted_tickets = []
            for ticket in tickets:
                formatted_tickets.append({
                    'ticket_id': str(ticket['_id']),
                    'subject': ticket['subject'],
                    'status': ticket['status'],
                    'priority': ticket['priority'],
                    'category': ticket['category'],
                    'created_at': ticket['created_at'].isoformat(),
                    'last_message': ticket['messages'][-1]['message'][:100] + '...' if ticket['messages'] else '',
                    'message_count': len(ticket['messages'])
                })
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Error getting user tickets: {e}")
            return []
    
    async def resolve_ticket(self, ticket_id: str, admin_id: int, resolution: str) -> Dict[str, Any]:
        """Resolve a support ticket"""
        try:
            await self.db.support_tickets.update_one(
                {'_id': ticket_id},
                {
                    '$set': {
                        'status': TicketStatus.RESOLVED.value,
                        'resolution': resolution,
                        'resolved_by': admin_id,
                        'resolved_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    },
                    '$push': {
                        'messages': {
                            'sender_id': admin_id,
                            'sender_type': 'admin',
                            'message': f"Ticket resolved: {resolution}",
                            'timestamp': datetime.utcnow()
                        }
                    }
                }
            )
            
            return {'success': True, 'status': TicketStatus.RESOLVED.value}
            
        except Exception as e:
            logger.error(f"Error resolving ticket: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_admin_tickets(self, admin_id: Optional[int] = None, 
                              status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get tickets for admin dashboard"""
        try:
            query = {}
            if admin_id:
                query['assigned_to'] = admin_id
            if status:
                query['status'] = status
            
            tickets = await self.db.support_tickets.find(query).sort('priority', -1).sort('created_at', 1).to_list(None)
            
            formatted_tickets = []
            for ticket in tickets:
                # Get user info
                user = await self.db.users.find_one({'user_id': ticket['user_id']})
                username = user.get('username', 'Unknown') if user else 'Unknown'
                
                formatted_tickets.append({
                    'ticket_id': str(ticket['_id']),
                    'user_id': ticket['user_id'],
                    'username': username,
                    'subject': ticket['subject'],
                    'status': ticket['status'],
                    'priority': ticket['priority'],
                    'category': ticket['category'],
                    'created_at': ticket['created_at'].isoformat(),
                    'assigned_to': ticket.get('assigned_to'),
                    'message_count': len(ticket['messages']),
                    'last_activity': ticket['updated_at'].isoformat()
                })
            
            return formatted_tickets
            
        except Exception as e:
            logger.error(f"Error getting admin tickets: {e}")
            return []
    
    async def search_faq(self, query: str) -> List[Dict[str, Any]]:
        """Search FAQ for relevant answers"""
        try:
            query_lower = query.lower()
            relevant_faqs = []
            
            for faq in self.faq_data:
                # Simple keyword matching
                if (query_lower in faq['question'].lower() or 
                    query_lower in faq['answer'].lower() or
                    any(keyword in query_lower for keyword in faq.get('keywords', []))):
                    relevant_faqs.append(faq)
            
            # Sort by relevance (simple scoring)
            for faq in relevant_faqs:
                score = 0
                if query_lower in faq['question'].lower():
                    score += 10
                if query_lower in faq['answer'].lower():
                    score += 5
                faq['relevance_score'] = score
            
            relevant_faqs.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            return relevant_faqs[:5]  # Return top 5 results
            
        except Exception as e:
            logger.error(f"Error searching FAQ: {e}")
            return []
    
    async def get_support_stats(self) -> Dict[str, Any]:
        """Get support system statistics"""
        try:
            total_tickets = await self.db.support_tickets.count_documents({})
            open_tickets = await self.db.support_tickets.count_documents({'status': TicketStatus.OPEN.value})
            resolved_tickets = await self.db.support_tickets.count_documents({'status': TicketStatus.RESOLVED.value})
            
            # Average resolution time
            resolved_with_time = await self.db.support_tickets.find({
                'status': TicketStatus.RESOLVED.value,
                'resolved_at': {'$exists': True}
            }).to_list(None)
            
            avg_resolution_hours = 0
            if resolved_with_time:
                total_hours = sum(
                    (ticket['resolved_at'] - ticket['created_at']).total_seconds() / 3600
                    for ticket in resolved_with_time
                )
                avg_resolution_hours = total_hours / len(resolved_with_time)
            
            # Tickets by category
            category_stats = await self.db.support_tickets.aggregate([
                {'$group': {'_id': '$category', 'count': {'$sum': 1}}}
            ]).to_list(None)
            
            return {
                'total_tickets': total_tickets,
                'open_tickets': open_tickets,
                'resolved_tickets': resolved_tickets,
                'resolution_rate': (resolved_tickets / total_tickets * 100) if total_tickets > 0 else 0,
                'avg_resolution_hours': round(avg_resolution_hours, 2),
                'category_breakdown': {stat['_id']: stat['count'] for stat in category_stats}
            }
            
        except Exception as e:
            logger.error(f"Error getting support stats: {e}")
            return {}
    
    def _load_faq_data(self) -> List[Dict[str, Any]]:
        """Load FAQ data"""
        return [
            {
                'id': 1,
                'question': 'How do I upload an account?',
                'answer': 'Click "Upload Account" in the seller bot, then send your session file or use OTP method.',
                'keywords': ['upload', 'session', 'file', 'account'],
                'category': 'selling'
            },
            {
                'id': 2,
                'question': 'How long does verification take?',
                'answer': 'Account verification typically takes 1-24 hours depending on queue size.',
                'keywords': ['verification', 'approve', 'time', 'wait'],
                'category': 'selling'
            },
            {
                'id': 3,
                'question': 'What payment methods are accepted?',
                'answer': 'We accept UPI payments and cryptocurrency (USDT, Bitcoin).',
                'keywords': ['payment', 'upi', 'crypto', 'bitcoin', 'usdt'],
                'category': 'payment'
            },
            {
                'id': 4,
                'question': 'How do I get my earnings?',
                'answer': 'Request payout from your balance in the seller bot. Minimum payout is $10.',
                'keywords': ['payout', 'earnings', 'withdraw', 'balance'],
                'category': 'payment'
            },
            {
                'id': 5,
                'question': 'Account was rejected, why?',
                'answer': 'Accounts may be rejected for: invalid session, banned account, incomplete profile, or quality issues.',
                'keywords': ['rejected', 'denied', 'banned', 'invalid'],
                'category': 'selling'
            }
        ]
    
    def _get_response_time(self, priority: str) -> str:
        """Get estimated response time based on priority"""
        response_times = {
            'urgent': '1-2 hours',
            'high': '2-6 hours',
            'medium': '6-24 hours',
            'low': '24-48 hours'
        }
        return response_times.get(priority, '24-48 hours')
    
    async def _auto_assign_ticket(self, ticket_id: str, category: str):
        """Auto-assign ticket to appropriate admin"""
        try:
            # Simple round-robin assignment
            # In production, you might want more sophisticated assignment logic
            admins = await self.db.users.find({'user_type': 'admin', 'is_active': True}).to_list(None)
            
            if admins:
                # Get admin with least assigned tickets
                admin_workload = {}
                for admin in admins:
                    count = await self.db.support_tickets.count_documents({
                        'assigned_to': admin['user_id'],
                        'status': {'$in': [TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value]}
                    })
                    admin_workload[admin['user_id']] = count
                
                # Assign to admin with least workload
                assigned_admin = min(admin_workload.items(), key=lambda x: x[1])[0]
                
                await self.db.support_tickets.update_one(
                    {'_id': ticket_id},
                    {'$set': {'assigned_to': assigned_admin}}
                )
                
        except Exception as e:
            logger.error(f"Error auto-assigning ticket: {e}")