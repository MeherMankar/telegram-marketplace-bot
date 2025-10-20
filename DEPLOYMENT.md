# Deployment Guide

## 🚀 Cloud Platform Deployment

### 1. Heroku Deployment

#### One-Click Deploy
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

#### Manual Deploy
```bash
# Install Heroku CLI
# Login to Heroku
heroku login

# Create app
heroku create your-app-name

# Set environment variables
heroku config:set BUYER_BOT_TOKEN=your_token
heroku config:set SELLER_BOT_TOKEN=your_token
heroku config:set ADMIN_BOT_TOKEN=your_token
heroku config:set MONGO_URI=your_mongodb_uri
heroku config:set SESSION_ENCRYPTION_KEY=your_32_byte_key
# Razorpay settings will be configured via admin bot
heroku config:set ADMIN_USER_IDS=123456789,987654321

# Add Redis addon
heroku addons:create heroku-redis:mini

# Deploy
git push heroku main
```

### 2. Render Deployment

1. **Connect Repository**: Link your GitHub repo to Render
2. **Create Web Service**: Use `render.yaml` configuration
3. **Set Environment Variables**: Add all required env vars in Render dashboard
4. **Deploy**: Render will auto-deploy from your repo

### 3. Koyeb Deployment

```bash
# Install Koyeb CLI
curl -fsSL https://cli.koyeb.com/install.sh | bash

# Login
koyeb auth login

# Deploy using config
koyeb app deploy --config koyeb.yaml

# Or deploy directly
koyeb service create \
  --app telegram-marketplace \
  --git github.com/yourusername/TGACbuysellbot \
  --git-branch main \
  --instance-type nano \
  --env BUYER_BOT_TOKEN=your_token \
  --env SELLER_BOT_TOKEN=your_token \
  --env MONGO_URI=your_mongodb_uri \
  --ports 8000:http \
  --routes /:8000
```

## 🗄️ Database Setup

### MongoDB Atlas (Recommended)
1. Create account at [MongoDB Atlas](https://cloud.mongodb.com)
2. Create cluster (free tier available)
3. Get connection string
4. Add to `MONGO_URI` environment variable

### Local MongoDB
```bash
# Using Docker
docker run -d -p 27017:27017 --name mongodb mongo:7.0

# Connection string
MONGO_URI=mongodb://localhost:27017/telegram_marketplace
```

## 🔧 Environment Variables

### Required Variables
```env
BUYER_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
SELLER_BOT_TOKEN=0987654321:ZYXwvuTSRqpONMlkJIhgFEDcba
ADMIN_BOT_TOKEN=1122334455:AdminBotTokenHere
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/telegram_marketplace
SESSION_ENCRYPTION_KEY=your-32-byte-encryption-key-here-12345
# Razorpay settings configured via admin bot
ADMIN_USER_IDS=123456789,987654321
```

### Optional Variables
```env
DEFAULT_PRICE_TABLE_JSON={"IN": {"2025": 40, "2024": 30}}
SIMULATE_UPI=false
SIMULATE_CRYPTO=false
REDIS_URL=redis://localhost:6379
```

## 🐳 Docker Deployment

### Local Development
```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Production Docker
```bash
# Build image
docker build -t telegram-marketplace .

# Run container
docker run -d \
  -p 8000:8000 \
  -e BUYER_BOT_TOKEN=your_token \
  -e SELLER_BOT_TOKEN=your_token \
  -e MONGO_URI=your_mongodb_uri \
  --name telegram-marketplace \
  telegram-marketplace
```

## 🔗 Webhook Configuration

### Razorpay Webhooks
1. Go to Razorpay Dashboard → Settings → Webhooks
2. Add webhook URL: `https://yourdomain.com/razorpay/webhook`
3. Select events: `payment.captured`, `payment.failed`
4. Add webhook secret to `RAZORPAY_WEBHOOK_SECRET`

### Telegram Webhooks (Optional)
```bash
# Set webhook for each bot
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://yourdomain.com/webhook/buyer"}'
```

## 📊 Monitoring & Logs

### Heroku Logs
```bash
heroku logs --tail -a your-app-name
```

### Render Logs
Available in Render dashboard under service logs

### Koyeb Logs
```bash
koyeb service logs telegram-marketplace
```

## 🔒 Security Checklist

- [ ] Use strong encryption keys (32+ characters)
- [ ] Enable HTTPS for webhooks
- [ ] Restrict admin user IDs
- [ ] Use production Razorpay keys
- [ ] Enable MongoDB authentication
- [ ] Set up proper firewall rules
- [ ] Regular security updates

## 🚨 Troubleshooting

### Common Issues

**Bot not responding**
- Check bot tokens are valid
- Verify webhook URLs are accessible
- Check environment variables

**Database connection failed**
- Verify MongoDB URI format
- Check network connectivity
- Ensure database exists

**Payment verification failed**
- Check Razorpay API keys
- Verify webhook signature
- Check webhook URL accessibility

### Health Check Endpoints
- `GET /health` - Application health
- `GET /webhook/test` - Webhook connectivity

## 📈 Scaling

### Horizontal Scaling
- Use load balancer for multiple instances
- Implement Redis for session storage
- Use MongoDB replica sets

### Performance Optimization
- Enable Redis caching
- Optimize database queries
- Use CDN for static assets
- Monitor resource usage

## 🔄 Updates & Maintenance

### Automated Deployment
Set up CI/CD pipeline with GitHub Actions:

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to Heroku
        uses: akhileshns/heroku-deploy@v3.12.12
        with:
          heroku_api_key: ${{secrets.HEROKU_API_KEY}}
          heroku_app_name: "your-app-name"
          heroku_email: "your-email@example.com"
```

### Database Backup
```bash
# MongoDB backup
mongodump --uri="your_mongodb_uri" --out=backup/

# Restore
mongorestore --uri="your_mongodb_uri" backup/
```