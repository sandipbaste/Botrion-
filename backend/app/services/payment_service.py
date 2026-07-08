
import os
import json
import hashlib
import hmac
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import socket

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL").rstrip('/')

class PaymentService:
    def __init__(self):
        # Database connection
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT', 5432))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.schema = os.getenv('DB_SCHEMA', 'Botrion')
        
        # Razorpay configuration
        self.razorpay_key_id = os.getenv('RAZORPAY_KEY_ID')
        self.razorpay_key_secret = os.getenv('RAZORPAY_KEY_SECRET')
        
        try:
            self.initialize_payment_tables()
        except Exception as e:
            print(f"⚠️ Payment tables initialization skipped (connection issue): {e}")
        
        self.start_reminder_thread()
    
    def get_connection(self):
        """Get database connection"""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=60,
                sslmode='require'
            )
            conn.autocommit = True
            
            # Set schema after connection
            cursor = conn.cursor()
            cursor.execute(f"SET search_path TO {self.schema}")
            cursor.close()
            
            return conn
        except Exception as e:
            print(f"  Database connection error: {e}")
            raise
    
    def initialize_payment_tables(self):
        """Initialize payment tables if they don't exist"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(f"SET search_path TO {self.schema}")
            
            # Check if tables exist
            cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'subscription_plans')")
            if not cursor.fetchone()[0]:
                print(" Tables will be created by schema.sql")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(" Payment tables verified successfully")
            
        except Exception as e:
            print(f"  Payment table initialization error: {e}")
    
    def start_reminder_thread(self):
        """Start background thread to check expiring subscriptions and send reminders"""
        def reminder_worker():
            while True:
                try:
                    self.check_and_send_reminders()
                except Exception as e:
                    print(f"  Reminder worker error: {e}")
                time.sleep(60)
        
        thread = threading.Thread(target=reminder_worker, daemon=True)
        thread.start()
        print(" Subscription reminder thread started (checking every minute)")
    
    def check_and_send_reminders(self):
        """Check for expiring subscriptions and send reminders"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT us.*, u.email, u.full_name, sp.plan_name, sp.price
                FROM user_subscriptions us
                JOIN users u ON us.user_id = u.id
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.payment_status = 'completed'
                AND us.subscription_status = 'active'
                AND us.end_date IS NOT NULL
                AND us.end_date > CURRENT_TIMESTAMP
                ORDER BY us.end_date ASC
            ''')
            
            subscriptions = cursor.fetchall()
            
            for sub in subscriptions:
                end_date = sub['end_date']
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                
                days_remaining = (end_date - datetime.now()).days
                
                if days_remaining <= 0:
                    continue
                
                reminder_days = [5, 4, 3, 2, 1]
                
                sent_reminders = []
                if sub.get('sent_reminders'):
                    try:
                        sent_reminders = [int(x) for x in sub['sent_reminders'].split(',') if x]
                    except:
                        sent_reminders = []
                
                if days_remaining in reminder_days and days_remaining not in sent_reminders:
                    self.send_expiry_reminder_email(
                        user_email=sub['email'],
                        user_name=sub['full_name'],
                        plan_name=sub['plan_name'],
                        days_remaining=days_remaining,
                        end_date=end_date
                    )
                    
                    sent_reminders.append(days_remaining)
                    cursor.execute('''
                        UPDATE user_subscriptions 
                        SET sent_reminders = %s 
                        WHERE id = %s
                    ''', (','.join(str(x) for x in sent_reminders), sub['id']))
                    
                    print(f"✅ Sent reminder to {sub['email']} at {days_remaining} days remaining")
            
            cursor.execute('''
                SELECT us.*, u.email, u.full_name, sp.plan_name
                FROM user_subscriptions us
                JOIN users u ON us.user_id = u.id
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.payment_status = 'completed'
                AND us.subscription_status = 'active'
                AND us.end_date IS NOT NULL
                AND us.end_date <= CURRENT_TIMESTAMP
            ''')
            
            expired_subs = cursor.fetchall()
            
            for sub in expired_subs:
                end_date = sub['end_date']
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                
                sent_reminders = []
                if sub.get('sent_reminders'):
                    try:
                        sent_reminders = [int(x) for x in sub['sent_reminders'].split(',') if x]
                    except:
                        sent_reminders = []
                
                if 0 not in sent_reminders:
                    self.send_final_expiry_email(
                        user_email=sub['email'],
                        user_name=sub['full_name'],
                        plan_name=sub['plan_name'],
                        end_date=end_date
                    )
                    
                    sent_reminders.append(0)
                    cursor.execute('''
                        UPDATE user_subscriptions 
                        SET sent_reminders = %s,
                            subscription_status = 'expired'
                        WHERE id = %s
                    ''', (','.join(str(x) for x in sent_reminders), sub['id']))
                    
                    print(f"📧 Sent final expiry email to {sub['email']}")
                else:
                    cursor.execute('''
                        UPDATE user_subscriptions 
                        SET subscription_status = 'expired' 
                        WHERE id = %s
                    ''', (sub['id'],))
                    
                    print(f"⚠️ Marked subscription as expired for {sub['email']}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Check reminders error: {e}")
            import traceback
            traceback.print_exc()
    
    def send_expiry_reminder_email(self, user_email: str, user_name: str, plan_name: str, days_remaining: int, end_date: datetime):
        """Send expiry reminder email"""
        try:
            from app.services.email_service import email_service
            
            if days_remaining == 1:
                subject = f"⚠️ URGENT: Your {plan_name} Plan Expires TOMORROW!"
            else:
                subject = f"⚠️ Reminder: Your {plan_name} Plan Expires in {days_remaining} Days"
            
            expiry_date = end_date.strftime('%B %d, %Y')
            
            if days_remaining <= 2:
                header_color = '#dc2626'
                urgency_text = "URGENT"
            elif days_remaining <= 3:
                header_color = '#f97316'
                urgency_text = "IMPORTANT"
            else:
                header_color = '#f59e0b'
                urgency_text = "REMINDER"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, {header_color}, {'#b91c1c' if days_remaining <= 2 else '#d97706'}); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ padding: 30px; background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 10px 10px; }}
                    .warning {{ background: {'#fee2e2' if days_remaining <= 2 else '#fef3c7'}; border-left: 4px solid {header_color}; padding: 15px; margin: 20px 0; border-radius: 8px; }}
                    .timer {{ font-size: 48px; font-weight: bold; color: {header_color}; text-align: center; margin: 20px 0; }}
                    .button {{ display: inline-block; background: linear-gradient(135deg, {header_color}, {'#b91c1c' if days_remaining <= 2 else '#d97706'}); color: white; padding: 12px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: bold; }}
                    .footer {{ text-align: center; padding: 20px; color: #6b7280; font-size: 12px; border-top: 1px solid #e5e7eb; margin-top: 20px; }}
                    .days-badge {{
                        display: inline-block;
                        background: {header_color};
                        color: white;
                        padding: 8px 20px;
                        border-radius: 25px;
                        font-size: 16px;
                        font-weight: bold;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>⚠️ {urgency_text}</h1>
                        <p>Your subscription requires attention</p>
                    </div>
                    <div class="content">
                        <div style="text-align: center;">
                            <div class="days-badge">
                                {days_remaining} Day{'s' if days_remaining > 1 else ''} Remaining
                            </div>
                        </div>
                        
                        <h2>Hello {user_name},</h2>
                        <p>Your <strong>{plan_name}</strong> subscription will expire in <strong>{days_remaining} day{'s' if days_remaining > 1 else ''}</strong> on <strong>{expiry_date}</strong>.</p>
                        
                        <div class="timer">
                            📅 {days_remaining}
                        </div>
                        
                        <div class="warning">
                            <p><strong>⚠️ What happens after expiry?</strong></p>
                            <p>• Your AI chatbots will stop working</p>
                            <p>• Visitors won't be able to chat with your bot</p>
                            <p>• Your data remains safe for 30 days</p>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="{FRONTEND_URL}/pricing" class="button">🔄 Renew Now →</a>
                        </div>
                    </div>
                    <div class="footer">
                        <p>© 2024 Botrion. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            email_service.send_email(
                to_email=user_email,
                subject=subject,
                body="",
                html_body=html_body
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending expiry reminder email: {e}")
            return False
    
    def send_final_expiry_email(self, user_email: str, user_name: str, plan_name: str, end_date: datetime):
        """Send final expiry email"""
        try:
            from app.services.email_service import email_service
            
            subject = f"❌ Your {plan_name} Plan Has Expired"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #dc2626, #991b1b); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ padding: 30px; background: #fff; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 10px 10px; }}
                    .warning {{ background: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; border-radius: 8px; }}
                    .button {{ display: inline-block; background: linear-gradient(135deg, #f97316, #ea580c); color: white; padding: 12px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: bold; }}
                    .footer {{ text-align: center; padding: 20px; color: #6b7280; font-size: 12px; border-top: 1px solid #e5e7eb; margin-top: 20px; }}
                    .expiry-date {{
                        font-size: 24px;
                        font-weight: bold;
                        color: #dc2626;
                        text-align: center;
                        margin: 20px 0;
                        padding: 15px;
                        background: #fef2f2;
                        border-radius: 10px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>❌ Subscription Expired</h1>
                        <p>Your plan is no longer active</p>
                    </div>
                    <div class="content">
                        <h2>Hello {user_name},</h2>
                        <p>Your <strong>{plan_name}</strong> subscription has expired on <strong>{end_date.strftime('%B %d, %Y')}</strong>.</p>
                        
                        <div class="expiry-date">
                            📅 Expired on: {end_date.strftime('%Y-%m-%d')}
                        </div>
                        
                        <div class="warning">
                            <p><strong>❌ Your account has been restricted:</strong></p>
                            <ul>
                                <li>All AI chatbots are <strong>disabled</strong></li>
                                <li>Chat widget is <strong>removed</strong> from your website</li>
                                <li>New conversations are <strong>blocked</strong></li>
                            </ul>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="{FRONTEND_URL}/pricing" class="button">🔄 Renew Now & Restore →</a>
                        </div>
                        
                        <div style="background: #f0fdf4; padding: 15px; border-radius: 10px; margin-top: 20px; border: 1px solid #86efac;">
                            <p><strong>✅ Good News - Your Data is Safe!</strong></p>
                            <p>• All chatbot configurations are preserved<br>
                            • Chat history is saved<br>
                            • Training data remains intact<br>
                            • Simply renew to restore everything instantly</p>
                        </div>
                    </div>
                    <div class="footer">
                        <p>© 2024 Botrion. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            email_service.send_email(
                to_email=user_email,
                subject=subject,
                body="",
                html_body=html_body
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending final expiry email: {e}")
            return False
    
    def check_subscription_active(self, user_id: int) -> Dict[str, Any]:
        """Check if user has an active subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT us.*, sp.plan_name, sp.price, sp.duration_days,
                    sp.max_websites, sp.max_chat_messages, sp.max_uploads,
                    sp.features,
                    CASE 
                        WHEN us.end_date IS NULL THEN 999
                        ELSE EXTRACT(EPOCH FROM (us.end_date - CURRENT_TIMESTAMP)) / 60
                    END as minutes_remaining
                FROM user_subscriptions us
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.user_id = %s 
                AND us.payment_status = 'completed'
                AND us.subscription_status = 'active'
                AND (us.end_date IS NULL OR us.end_date > CURRENT_TIMESTAMP)
                ORDER BY us.end_date DESC
                LIMIT 1
            ''', (user_id,))
            
            subscription = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if subscription:
                minutes_remaining = subscription.get('minutes_remaining', 0)
                # Ensure minutes_remaining is a number
                if isinstance(minutes_remaining, str):
                    try:
                        minutes_remaining = float(minutes_remaining)
                    except:
                        minutes_remaining = 0
                
                is_active = minutes_remaining > 0 or subscription.get('end_date') is None
                
                return {
                    "success": True,
                    "has_subscription": True,
                    "is_active": is_active,
                    "subscription": subscription,
                    "minutes_remaining": int(minutes_remaining) if minutes_remaining > 0 else 0
                }
            else:
                # Check if user has a free trial
                cursor.execute('''
                    SELECT us.*, sp.plan_name, sp.price, sp.duration_days,
                        sp.max_websites, sp.max_chat_messages, sp.max_uploads,
                        sp.features,
                        CASE 
                            WHEN us.end_date IS NULL THEN 999
                            ELSE EXTRACT(EPOCH FROM (us.end_date - CURRENT_TIMESTAMP)) / 60
                        END as minutes_remaining
                    FROM user_subscriptions us
                    JOIN subscription_plans sp ON us.plan_id = sp.id
                    WHERE us.user_id = %s 
                    AND us.payment_status = 'completed'
                    AND us.subscription_status = 'active'
                    AND sp.price = 0
                    ORDER BY us.end_date DESC
                    LIMIT 1
                ''', (user_id,))
                
                trial = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if trial:
                    minutes_remaining = trial.get('minutes_remaining', 0)
                    if isinstance(minutes_remaining, str):
                        try:
                            minutes_remaining = float(minutes_remaining)
                        except:
                            minutes_remaining = 0
                    
                    is_active = minutes_remaining > 0
                    
                    return {
                        "success": True,
                        "has_subscription": True,
                        "is_active": is_active,
                        "subscription": trial,
                        "minutes_remaining": int(minutes_remaining) if minutes_remaining > 0 else 0,
                        "is_trial": True
                    }
                
                return {
                    "success": True,
                    "has_subscription": False,
                    "is_active": False,
                    "subscription": None,
                    "minutes_remaining": 0
                }
                
        except Exception as e:
            print(f"  Check subscription error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "has_subscription": False,
                "is_active": False,
                "minutes_remaining": 0
            }
    
    def get_user_subscription(self, user_id: int) -> Dict[str, Any]:
        """Get user's active subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT us.*, sp.plan_name, sp.price, sp.duration_days,
                       sp.max_websites, sp.max_chat_messages, sp.max_uploads,
                       sp.features,
                       CASE 
                         WHEN us.end_date IS NULL THEN 999
                         ELSE EXTRACT(EPOCH FROM (us.end_date - CURRENT_TIMESTAMP)) / 60
                       END as minutes_remaining
                FROM user_subscriptions us
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.user_id = %s 
                AND us.payment_status = 'completed'
                AND us.subscription_status = 'active'
                ORDER BY us.end_date DESC
                LIMIT 1
            ''', (user_id,))
            
            subscription = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            has_subscription = subscription is not None
            is_active = has_subscription and subscription.get('minutes_remaining', 0) > 0
            
            return {
                "success": True,
                "has_subscription": has_subscription,
                "is_active": is_active,
                "subscription": subscription,
                "minutes_remaining": subscription.get('minutes_remaining', 0) if subscription else 0
            }
            
        except Exception as e:
            print(f"  Get user subscription error: {e}")
            return {
                "success": False, 
                "error": str(e), 
                "has_subscription": False,
                "is_active": False,
                "minutes_remaining": 0
            }
    
    def create_payment_order(self, user_id: int, plan_id: int) -> Dict[str, Any]:
        """Create a payment order for subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get plan details
            cursor.execute('SELECT * FROM subscription_plans WHERE id = %s', (plan_id,))
            plan = cursor.fetchone()
            
            if not plan:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Plan not found"}
            
            # Check if user already has an active subscription
            cursor.execute('''
                SELECT * FROM user_subscriptions 
                WHERE user_id = %s 
                AND payment_status = 'completed'
                AND subscription_status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (user_id,))
            
            existing_subscription = cursor.fetchone()
            
            # Generate unique order IDs
            timestamp = int(datetime.now().timestamp())
            our_order_id = f"order_{user_id}_{timestamp}"
            transaction_id = f"txn_{user_id}_{timestamp}"
            
            # Calculate end date - 30 days
            duration_days = 30
            end_date = datetime.now() + timedelta(days=duration_days)
            
            # Create subscription record
            cursor.execute('''
                INSERT INTO user_subscriptions 
                (user_id, plan_id, payment_id, amount_paid, currency, 
                payment_status, subscription_status, end_date, sent_reminders)
                VALUES (%s, %s, %s, %s, %s, 'pending', 'active', %s, '')
                RETURNING id
            ''', (
                user_id,
                plan_id,
                our_order_id,
                plan['price'],
                plan.get('currency', 'INR'),
                end_date
            ))
            
            subscription_id = cursor.fetchone()['id']
            
            # Create payment transaction
            cursor.execute('''
                INSERT INTO payment_transactions 
                (user_id, subscription_id, transaction_id, amount, currency, status, gateway_response)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                RETURNING id
            ''', (
                user_id,
                subscription_id,
                transaction_id,
                plan['price'],
                plan.get('currency', 'INR'),
                json.dumps({'our_order_id': our_order_id})
            ))
            
            conn.commit()
            
            # Prepare payment data
            payment_data = {
                'our_order_id': our_order_id,
                'amount': plan['price'],
                'currency': plan.get('currency', 'INR'),
                'plan_name': plan['plan_name'],
                'subscription_id': subscription_id
            }
            
            # If Razorpay is configured, create Razorpay order
            if self.razorpay_key_id and self.razorpay_key_secret:
                try:
                    import razorpay
                    client = razorpay.Client(auth=(self.razorpay_key_id, self.razorpay_key_secret))
                    
                    amount_in_paise = int(plan['price'] * 100)
                    
                    razorpay_order = client.order.create({
                        'amount': amount_in_paise,
                        'currency': plan.get('currency', 'INR'),
                        'receipt': our_order_id,
                        'notes': {
                            'user_id': user_id,
                            'plan_id': plan_id,
                            'subscription_id': subscription_id
                        },
                        'payment_capture': 1
                    })
                    
                    payment_data['razorpay_order_id'] = razorpay_order['id']
                    payment_data['razorpay_key'] = self.razorpay_key_id
                    
                    # Update gateway_response with Razorpay order details
                    cursor.execute('''
                        UPDATE payment_transactions 
                        SET gateway_response = gateway_response || %s
                        WHERE subscription_id = %s
                    ''', (json.dumps({
                        'razorpay_order_id': razorpay_order['id'],
                        'razorpay_order': razorpay_order
                    }), subscription_id))
                    
                    conn.commit()
                    
                except ImportError:
                    print(" Razorpay not installed")
                except Exception as e:
                    print(f" Razorpay order creation error: {e}")
                    payment_data['test_mode'] = True
            
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": "Payment order created successfully",
                "order_id": our_order_id,
                "subscription_id": subscription_id,
                "plan": {
                    "id": plan['id'],
                    "plan_name": plan['plan_name'],
                    "price": plan['price'],
                    "duration_days": plan.get('duration_days', 30)
                },
                "payment_data": payment_data,
                "existing_subscription": existing_subscription
            }
            
        except Exception as e:
            print(f"  Create payment order error: {e}")
            return {"success": False, "error": str(e)}
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify payment and update subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            razorpay_payment_id = payment_data.get('razorpay_payment_id')
            razorpay_order_id = payment_data.get('razorpay_order_id')
            razorpay_signature = payment_data.get('razorpay_signature')
            our_order_id = payment_data.get('our_order_id')
            
            # Verify signature if using Razorpay
            if self.razorpay_key_secret and razorpay_signature and razorpay_order_id and razorpay_payment_id:
                try:
                    generated_signature = hmac.new(
                        self.razorpay_key_secret.encode(),
                        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
                        hashlib.sha256
                    ).hexdigest()
                    
                    if generated_signature != razorpay_signature:
                        cursor.close()
                        conn.close()
                        return {"success": False, "error": "Invalid payment signature"}
                except Exception as sig_error:
                    print(f" Signature verification error: {sig_error}")
            
            # Find the subscription
            subscription = None
            
            if our_order_id:
                cursor.execute('''
                    SELECT us.*, u.email, u.full_name, u.id as user_id
                    FROM user_subscriptions us
                    JOIN users u ON us.user_id = u.id
                    WHERE us.payment_id = %s AND us.payment_status = 'pending'
                ''', (our_order_id,))
                subscription = cursor.fetchone()
            
            if not subscription and razorpay_order_id:
                cursor.execute('''
                    SELECT pt.subscription_id 
                    FROM payment_transactions pt
                    WHERE pt.gateway_response::text LIKE %s
                ''', (f'%{razorpay_order_id}%',))
                transaction = cursor.fetchone()
                if transaction and transaction.get('subscription_id'):
                    cursor.execute('''
                        SELECT us.*, u.email, u.full_name, u.id as user_id
                        FROM user_subscriptions us
                        JOIN users u ON us.user_id = u.id
                        WHERE us.id = %s
                    ''', (transaction['subscription_id'],))
                    subscription = cursor.fetchone()
            
            if not subscription:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Subscription not found"}
            
            # Update subscription status
            cursor.execute('''
                UPDATE user_subscriptions 
                SET payment_status = 'completed',
                    subscription_status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (subscription['id'],))
            
            # Update payment transaction
            gateway_update = {
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_order_id': razorpay_order_id,
                'razorpay_signature': razorpay_signature,
                'verified_at': datetime.now().isoformat()
            }
            
            cursor.execute('''
                UPDATE payment_transactions 
                SET status = 'completed',
                    gateway_response = gateway_response || %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE subscription_id = %s AND status = 'pending'
            ''', (json.dumps(gateway_update), subscription['id']))
            
            # Get plan details to update user table
            cursor.execute('''
                SELECT sp.plan_name, sp.duration_days, us.end_date
                FROM user_subscriptions us
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.id = %s
            ''', (subscription['id'],))
            
            plan_info = cursor.fetchone()
            
            # Update users table with subscription plan and end date
            if plan_info:
                cursor.execute('''
                    UPDATE users 
                    SET subscription_plan = %s,
                        subscription_end_date = %s
                    WHERE id = %s
                ''', (plan_info['plan_name'], subscription['end_date'], subscription['user_id']))
            
            # Get updated subscription
            cursor.execute('''
                SELECT us.*, sp.plan_name, sp.price, sp.duration_days,
                    sp.max_websites, sp.max_chat_messages, sp.max_uploads,
                    sp.features,
                    CASE 
                        WHEN us.end_date IS NULL THEN 999
                        ELSE EXTRACT(EPOCH FROM (us.end_date - CURRENT_TIMESTAMP)) / 60
                    END as minutes_remaining
                FROM user_subscriptions us
                JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE us.id = %s
            ''', (subscription['id'],))
            
            updated_subscription = cursor.fetchone()
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": "Payment verified and subscription activated successfully",
                "subscription": updated_subscription
            }
            
        except Exception as e:
            print(f"  Verify payment error: {e}")
            return {"success": False, "error": f"Payment verification failed: {str(e)}"}
    
    def get_subscription_plans(self) -> Dict[str, Any]:
        """Get all available subscription plans"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT * FROM subscription_plans 
                WHERE is_active = TRUE
                ORDER BY price ASC
            ''')
            
            plans = cursor.fetchall()
            
            for plan in plans:
                plan.setdefault('max_chat_messages', 0)
                plan.setdefault('max_websites', 0)
                plan.setdefault('max_uploads', 0)
                plan.setdefault('duration_days', 30)
                plan.setdefault('price', 0)
                
                if plan.get('features'):
                    try:
                        if isinstance(plan['features'], str):
                            plan['features'] = json.loads(plan['features'])
                    except:
                        plan['features'] = []
                else:
                    plan['features'] = []
            
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "plans": plans
            }
            
        except Exception as e:
            print(f"  Get subscription plans error: {e}")
            return {"success": False, "error": str(e), "plans": []}
    
    def check_user_access(self, user_id: int, action: str = "train") -> Dict[str, Any]:
        """Check if user can perform an action based on subscription"""
        subscription_result = self.get_user_subscription(user_id)
        
        if not subscription_result['success']:
            return {
                "success": False,
                "has_access": False,
                "message": "Unable to verify subscription",
                "requires_subscription": True,
                "is_expired": False
            }
        
        if not subscription_result['has_subscription']:
            return {
                "success": False,
                "has_access": False,
                "message": "No active subscription found",
                "requires_subscription": True,
                "is_expired": False
            }
        
        is_active = subscription_result['is_active']
        minutes_remaining = subscription_result['minutes_remaining']
        
        if not is_active or minutes_remaining <= 0:
            return {
                "success": False,
                "has_access": False,
                "message": "Your subscription has expired. Please recharge to continue.",
                "requires_subscription": True,
                "is_expired": True,
                "minutes_remaining": 0
            }
        
        subscription = subscription_result['subscription']
        
        # Check website count for training
        if action == "train":
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('SELECT COUNT(*) as count FROM websites WHERE user_id = %s', (user_id,))
            website_count = cursor.fetchone()['count']
            
            cursor.close()
            conn.close()
            
            max_websites = subscription.get('max_websites', 1)
            
            if website_count >= max_websites:
                return {
                    "success": False,
                    "has_access": False,
                    "message": f"Website limit reached ({max_websites} allowed)",
                    "current_count": website_count,
                    "max_allowed": max_websites,
                    "is_expired": False
                }
        
        return {
            "success": True,
            "has_access": True,
            "is_expired": False,
            "subscription": subscription,
            "minutes_remaining": minutes_remaining,
            "message": "Access granted"
        }
    
    def get_payment_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Get user's payment history"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT pt.*, sp.plan_name, us.payment_status
                FROM payment_transactions pt
                LEFT JOIN user_subscriptions us ON pt.subscription_id = us.id
                LEFT JOIN subscription_plans sp ON us.plan_id = sp.id
                WHERE pt.user_id = %s
                ORDER BY pt.created_at DESC
                LIMIT %s
            ''', (user_id, limit))
            
            history = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "history": history,
                "count": len(history)
            }
            
        except Exception as e:
            print(f"  Get payment history error: {e}")
            return {"success": False, "error": str(e), "history": []}
    
    def cancel_subscription(self, user_id: int, subscription_id: int) -> Dict[str, Any]:
        """Cancel user subscription"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT * FROM user_subscriptions 
                WHERE id = %s AND user_id = %s
            ''', (subscription_id, user_id))
            
            subscription = cursor.fetchone()
            
            if not subscription:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Subscription not found"}
            
            cursor.execute('''
                UPDATE user_subscriptions 
                SET subscription_status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (subscription_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {"success": True, "message": "Subscription cancelled successfully"}
            
        except Exception as e:
            print(f"  Cancel subscription error: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
payment_service = PaymentService()