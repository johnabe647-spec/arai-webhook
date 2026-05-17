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
    
    try:
        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False

def update_supabase(firm_id, tier, customer_id):
    """Update firm subscription using Supabase REST API"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials not set")
        return False
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
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
            "subscription_status": "active"
        }
        
        # Only add customer_id if provided
        if customer_id:
            data["lemonsqueezy_customer_id"] = customer_id
        
        response = requests.patch(update_url, headers=headers, json=data)
        
        if response.status_code == 200:
            print(f"Successfully updated firm {firm_id} to {tier} plan")
            return True
        else:
            print(f"Failed to update firm: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error updating firm: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Lemon Squeezy webhook events"""
    
    signature = request.headers.get('X-Signature')
    
    # Verify signature
    if not verify_signature(request.data, signature):
        print("Invalid signature received")
        return jsonify({"error": "Invalid signature"}), 401
    
    event = request.json
    
    if not event:
        print("No data received")
        return jsonify({"error": "No data received"}), 400
    
    event_name = event.get('meta', {}).get('event_name')
    print(f"Received webhook: {event_name}")
    
    # Debug: print full event for troubleshooting
    print(f"Event data: {json.dumps(event, indent=2)}")
    
    # Handle order creation (successful payment)
    if event_name == 'order_created':
        data = event.get('data', {}).get('attributes', {})
        custom_data = data.get('custom', {})
        firm_id = custom_data.get('firm_id')
        
        first_order_item = data.get('first_order_item', {})
        variant_id = str(first_order_item.get('variant_id', ''))
        
        # Determine subscription tier
        if variant_id == PROFESSIONAL_VARIANT_ID:
            tier = "professional"
        elif variant_id == ENTERPRISE_VARIANT_ID:
            tier = "enterprise"
        else:
            print(f"Unknown variant ID: {variant_id}")
            tier = "professional"
        
        customer_id = data.get('customer_id')
        
        print(f"Updating firm {firm_id} to {tier} plan (customer: {customer_id})")
        
        if firm_id:
            update_supabase(firm_id, tier, customer_id)
        else:
            print("No firm_id found in custom_data")
    
    # Handle subscription creation
    elif event_name == 'subscription_created':
        data = event.get('data', {}).get('attributes', {})
        custom_data = data.get('custom', {})
        firm_id = custom_data.get('firm_id')
        
        variant_id = str(data.get('variant_id', ''))
        
        if variant_id == PROFESSIONAL_VARIANT_ID:
            tier = "professional"
        elif variant_id == ENTERPRISE_VARIANT_ID:
            tier = "enterprise"
        else:
            tier = "professional"
        
        customer_id = data.get('customer_id')
        
        print(f"Subscription created for firm {firm_id} - {tier} plan")
        
        if firm_id:
            update_supabase(firm_id, tier, customer_id)
    
    # Handle subscription updated (plan changes, etc.)
    elif event_name == 'subscription_updated':
        data = event.get('data', {}).get('attributes', {})
        custom_data = data.get('custom', {})
        firm_id = custom_data.get('firm_id')
        
        status = data.get('status')
        variant_id = str(data.get('variant_id', ''))
        
        if status == 'cancelled':
            print(f"Subscription cancelled for firm {firm_id}")
            if firm_id:
                update_supabase(firm_id, "free", None)
        elif status == 'active':
            if variant_id == PROFESSIONAL_VARIANT_ID:
                tier = "professional"
            elif variant_id == ENTERPRISE_VARIANT_ID:
                tier = "enterprise"
            else:
                tier = "professional"
            
            print(f"Subscription updated for firm {firm_id} - {tier} plan")
            if firm_id:
                update_supabase(firm_id, tier, None)
    
    # Handle subscription cancellation
    elif event_name == 'subscription_cancelled':
        data = event.get('data', {}).get('attributes', {})
        custom_data = data.get('custom', {})
        firm_id = custom_data.get('firm_id')
        
        print(f"Subscription cancelled for firm {firm_id}")
        
        if firm_id:
            update_supabase(firm_id, "free", None)
    
    # Handle successful payment (for subscription renewal)
    elif event_name == 'subscription_payment_success':
        data = event.get('data', {}).get('attributes', {})
        print(f"Successful payment received for subscription")
        # Optionally update last_payment_date or other tracking
    
    return jsonify({"status": "ok"}), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/test-update', methods=['GET'])
def test_update():
    """Test endpoint to manually update a firm (for debugging)"""
    firm_id = request.args.get('firm_id')
    tier = request.args.get('tier', 'professional')
    
    if not firm_id:
        return jsonify({"error": "firm_id required"}), 400
    
    success = update_supabase(firm_id, tier, "test_customer_123")
    
    if success:
        return jsonify({"status": "success", "firm_id": firm_id, "tier": tier}), 200
    else:
        return jsonify({"error": "Update failed"}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)