# Render Deployment Guide

## Prerequisites
- GitHub account with repository pushed
- Render account (https://render.com)
- MongoDB Atlas account (free tier available)
- All bot tokens from Telegram BotFather

## Step 1: Prepare Repository
1. Push your code to GitHub
2. Ensure `.env.example` is in root (already created)
3. Add `Procfile` and `render.yaml` (already created)

## Step 2: Create MongoDB Atlas Database
1. Go to https://www.mongodb.com/cloud/atlas
2. Create free cluster
3. Create database user with password
4. Get connection string: `mongodb+srv://username:password@cluster.mongodb.net/telegram_marketplace?retryWrites=true&w=majority`

## Step 3: Deploy on Render
1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect GitHub repository
4. Configure:
   - **Name**: `telegram-marketplace`
   - **Runtime**: Python 3.11
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: Free (or Starter for production)

## Step 4: Set Environment Variables
In Render dashboard, add these environment variables:
```
API_ID=your_api_id
API_HASH=your_api_hash
BUYER_BOT_TOKEN=your_buyer_bot_token
SELLER_BOT_TOKEN=your_seller_bot_token
ADMIN_BOT_TOKEN=your_admin_bot_token
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/telegram_marketplace?retryWrites=true&w=majority
SESSION_ENCRYPTION_KEY=your-32-byte-encryption-key-here
DEFAULT_PRICE_TABLE_JSON={"IN": {"2025": 40, "2024": 30}, "US": {"2025": 50, "2024": 40}}
ADMIN_USER_IDS=your_admin_user_id
PORT=8000
```

## Step 5: Deploy
1. Click "Create Web Service"
2. Wait for build to complete (5-10 minutes)
3. Check logs for "All bots are running"

## Step 6: Keep Service Running
Render free tier services spin down after 15 minutes of inactivity. To keep running:

**Option A: Upgrade to Starter Plan** ($7/month)
- Keeps service always running
- Recommended for production

**Option B: Use Uptime Monitor**
1. Create free Uptime Monitor on Render
2. Point to your service's health endpoint
3. Pings every 5 minutes to keep alive

## Monitoring
- View logs: Dashboard → Logs tab
- Check health: `https://your-service.onrender.com/health`
- Monitor bots: Check Telegram for bot responses

## Troubleshooting

**Build fails**
- Check Python version compatibility
- Verify all dependencies in requirements.txt
- Check for syntax errors

**Bots not responding**
- Verify bot tokens are correct
- Check MongoDB connection string
- Review logs for errors

**Service keeps spinning down**
- Upgrade to Starter plan
- Or set up Uptime Monitor

## Cost Estimation
- **Free Tier**: $0 (spins down after 15 min inactivity)
- **Starter Plan**: $7/month (always running)
- **MongoDB Atlas**: Free tier (512MB storage)
- **Total**: ~$7/month for production

## Next Steps
1. Deploy to Render
2. Test all three bots
3. Monitor logs for errors
4. Set up backup strategy
