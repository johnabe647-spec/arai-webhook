from flask import Flask, request, jsonify
import hmac
import hashlib
import json
import requests
import os

app = Flask(__name__)

# Get environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
WEBHOOK_SECRET = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET")
PROFESSIONAL_VARIANT_ID = os.environ.get("PROFESSIONAL_VARIANT_ID")
ENTERPRISE_VARIANT_ID = os.environ.get("ENTERPRISE_VARIANT_ID")

def verify_signature(payload, signature):
    """Verify webhook signature from Lemon Squeezy"""
    if not WEBHOOK_SECRET:
        print("Warning: WEBHOOK_SECRET not set")
        return True
    
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

def update_supabase(firm_id, tier, customer_id):
    """Update firm subscription using Supabase REST API"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    # First, get the firm to verify it exists
    get_url = f"{SUPABASE_URL}/rest/v1/firms?id=eq.{firm_id}&select=id"
    response = requests.get(get_url, headers=headers)
    
    if response.status_code != 200 or not response.json():
        print(f"Firm {firm_id} not found")
        return False
    
    # Update the firm
    update_url = f"{SUPABASE_URL}/rest/v1/firms?id=eq.{firm_id}"
    data = {
        "subscription_tier": tier,
        "subscription_status": "active",
        "lemonsqueezy_customer_id": customer_id
    }
    
    response = requests.patch(update_url, headers=headers, json=data)
    return response.status_code == 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Lemon Squeezy webhook events"""
    
    signature = request.headers.get('X-Signature')
    
    if not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 401
    
    event = request.json
    
    if not event:
        return jsonify({"error": "No data received"}), 400
    
    event_name = event.get('meta', {}).get('event_name')
    print(f"Received webhook: {event_name}")
    
    if event_name == 'order_created':
        data = event.get('data', {}).get('attributes', {})
        custom_data = data.get('custom', {})
        firm_id = custom_data.get('firm_id')
        
        first_order_item = data.get('first_order_item', {})
        variant_id = str(first_order_item.get('variant_id', ''))
        
        if variant_id == PROFESSIONAL_VARIANT_ID:
            tier = "professional"
        elif variant_id == ENTERPRISE_VARIANT_ID:
            tier = "enterprise"
        else:
            tier = "professional"
        
        customer_id = data.get('customer_id')
        
        print(f"Updating firm {firm_id} to {tier} plan")
        
        if firm_id and customer_id:
            if update_supabase(firm_id, tier, customer_id):
                print(f"Successfully updated firm {firm_id}")
            else:
                print(f"Failed to update firm {firm_id}")
    
    return jsonify({"status": "ok"}), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(port=5000)
