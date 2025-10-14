# 🌐 Accessing Dashboard on devnet-2

## Overview

There are **3 ways** to access the web dashboard running on devnet-2. Choose based on your needs and DevOps policies.

---

## 🔐 Option 1: SSH Tunnel (Localhost) - **RECOMMENDED**

**Best for**: Secure access, testing, no firewall changes needed

### **How it works:**
```
Your Mac → SSH Tunnel → devnet-2:8000
           (encrypted)
```

### **Setup:**

```bash
# Create SSH tunnel (run this on your Mac)
ssh -L 8000:localhost:8000 root@injective-devnet-2 -N

# Explanation:
# -L 8000:localhost:8000  → Forward local port 8000 to remote port 8000
# -N                       → Don't execute remote commands
# This command will stay running (don't close the terminal)
```

**Keep this terminal open!** The tunnel stays active while this command runs.

### **Access Dashboard:**

Open your browser on Mac:
```
http://localhost:8000
```

**Login:**
- Username: `admin` (from .env on server)
- Password: `<your password from server .env>`

### **Advantages:**
- ✅ No firewall changes needed
- ✅ Encrypted connection via SSH
- ✅ Works immediately
- ✅ DevOps approval not required
- ✅ Most secure option

### **Disadvantages:**
- ❌ Must keep SSH connection open
- ❌ Only you can access (not team)
- ❌ Tunnel closes if SSH disconnects

### **Pro Tip:**

Keep tunnel running in background:
```bash
# Run in background (optional)
ssh -L 8000:localhost:8000 root@injective-devnet-2 -N -f

# Check if running
ps aux | grep "ssh.*8000"

# Kill background tunnel
pkill -f "ssh.*8000.*injective-devnet-2"
```

Or use a persistent session manager like `screen` or `tmux`:
```bash
# Using screen (if installed)
ssh root@injective-devnet-2

# On server
screen -S tunnel
ssh -L 8000:localhost:8000 localhost -N
# Press Ctrl+A, then D to detach
```

---

## 🌍 Option 2: Public IP Access - **REQUIRES DEVOPS**

**Best for**: Team access, production use, permanent setup

### **Find Server's Public IP:**

```bash
# SSH to devnet-2
ssh root@injective-devnet-2

# Get public IP
curl -s ifconfig.me
# or
curl -s api.ipify.org
```

Example output: `203.0.113.45`

### **Check if Port 8000 is Accessible:**

```bash
# From your Mac, test if port is open
nc -zv 203.0.113.45 8000

# or
curl -I http://203.0.113.45:8000
```

**If successful:**
```
Connection successful
HTTP/1.1 200 OK
```

**If blocked:**
```
Connection refused
Connection timed out
```

### **If Blocked: Request Firewall Rule from DevOps**

**Email/Slack to DevOps:**

```
Subject: Firewall Rule Request - Trading Bot Dashboard Access

Hi DevOps Team,

I need to access the trading bot web dashboard running on injective-devnet-2.

Request Details:
- Server: injective-devnet-2 (IP: <public-ip>)
- Port: 8000 (TCP)
- Service: Trading Bot Web Dashboard (HTTP)
- Access Required: Team members only (or your IP: <your-public-ip>)

Security:
- Dashboard has HTTP Basic Authentication (username/password)
- Running in Docker container
- Read-only dashboard for monitoring bots

Can you please:
1. Open port 8000 on injective-devnet-2 firewall?
2. Restrict to our team IPs if possible (provide list)

Let me know if you need any additional information.

Thanks!
```

**Alternative: Request specific IP whitelist**
```bash
# Get your public IP
curl -s ifconfig.me
# Example: 198.51.100.10

# Ask DevOps to whitelist: 198.51.100.10 → devnet-2:8000
```

### **Once Port is Open:**

Access dashboard:
```
http://203.0.113.45:8000
```

**Team members can access:**
```
http://203.0.113.45:8000
Username: admin
Password: <shared-password>
```

### **Advantages:**
- ✅ Team can access from anywhere
- ✅ No SSH tunnel needed
- ✅ Persistent access
- ✅ Easy to share URL

### **Disadvantages:**
- ❌ Requires DevOps approval
- ❌ Firewall changes needed
- ❌ Less secure (HTTP over internet)
- ❌ May take time to approve

### **Security Recommendations:**

If using public IP:

1. **Use HTTPS (not HTTP)** - Ask DevOps for reverse proxy with SSL
2. **Restrict IPs** - Whitelist only your team's IPs
3. **Strong password** - Use complex password in .env
4. **VPN access** - Request access only via company VPN
5. **Monitor access logs** - Check who's accessing

```bash
# Monitor access logs
docker compose logs web | grep "GET /api"
```

---

## 🔒 Option 3: Reverse Proxy with Domain - **PRODUCTION GRADE**

**Best for**: Production deployment, SSL/HTTPS, custom domain

### **Request from DevOps:**

```
Subject: Reverse Proxy Setup Request - Trading Bot Dashboard

Hi DevOps Team,

I'd like to set up a proper production URL for the trading bot dashboard.

Request:
- Setup reverse proxy (nginx/traefik) on devnet-2
- Domain: trading-bot.injective-devnet.company.com
- SSL Certificate (Let's Encrypt or company CA)
- Proxy to: localhost:8000 (Docker container)

Benefits:
- HTTPS (encrypted)
- Custom domain (easy to remember)
- SSL certificate validation
- Access logging
- Can add IP restrictions

Is this something you can help set up?

Thanks!
```

### **What DevOps Will Set Up:**

```
Browser → https://trading-bot.injective-devnet.company.com
              ↓ (SSL/HTTPS)
         Nginx/Traefik on devnet-2
              ↓
         localhost:8000 (Docker container)
```

### **Example Nginx Config (DevOps will create):**

```nginx
server {
    listen 443 ssl;
    server_name trading-bot.injective-devnet.company.com;

    ssl_certificate /etc/ssl/certs/trading-bot.crt;
    ssl_certificate_key /etc/ssl/private/trading-bot.key;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### **Access:**

```
https://trading-bot.injective-devnet.company.com
```

### **Advantages:**
- ✅ HTTPS (encrypted)
- ✅ Custom domain
- ✅ Production-ready
- ✅ SSL certificate
- ✅ Easy to remember
- ✅ Professional setup

### **Disadvantages:**
- ❌ Requires DevOps setup
- ❌ Takes longer to implement
- ❌ May require approvals
- ❌ Needs domain/DNS management

---

## 🎯 Recommended Approach

### **For Development/Testing:**
👉 **Use Option 1 (SSH Tunnel)**
- Quick, secure, no approvals needed
- Perfect for testing

### **For Team Use (QA):**
👉 **Use Option 2 (Public IP with Firewall Rule)**
- Request IP whitelist from DevOps
- Share URL with team
- Still secure with proper firewall

### **For Production:**
👉 **Use Option 3 (Reverse Proxy + Domain + SSL)**
- Proper HTTPS
- Custom domain
- Production-grade security

---

## 📝 Step-by-Step: Accessing Dashboard After Deployment

### **Immediate Access (SSH Tunnel):**

```bash
# 1. Start SSH tunnel on your Mac
ssh -L 8000:localhost:8000 root@injective-devnet-2 -N

# 2. Open browser (in another terminal/tab)
open http://localhost:8000

# 3. Login
# Username: admin
# Password: (from server's .env file)
```

### **Later: Request Public Access**

```bash
# 1. Find server public IP
ssh root@injective-devnet-2 "curl -s ifconfig.me"

# 2. Email DevOps with request (see templates above)

# 3. Once approved, share URL with team:
#    http://<public-ip>:8000
```

---

## 🔍 Verify Dashboard is Running on Server

Before trying to access:

```bash
# SSH to server
ssh root@injective-devnet-2

# Check container is running
docker compose ps
# Should show: trading-bot-web   Up

# Check port is listening
netstat -tlnp | grep 8000
# Should show: 0.0.0.0:8000 ... docker-proxy

# Test locally on server
curl -I http://localhost:8000
# Should return: HTTP/1.1 200 OK

# Test with auth
curl -u admin:your_password http://localhost:8000/api/health
# Should return: {"status": "healthy"}
```

---

## 🛠️ Troubleshooting Access

### **Problem: "Connection refused" via SSH tunnel**

**Solution:**
```bash
# Check dashboard is running on server
ssh root@injective-devnet-2 "docker compose ps"

# Check port binding
ssh root@injective-devnet-2 "netstat -tlnp | grep 8000"

# Restart dashboard
ssh root@injective-devnet-2 "cd /root/injective/injective-testnet-liquidity-bot && docker compose restart web"
```

---

### **Problem: "Connection timeout" via public IP**

**Causes:**
1. Port 8000 not open in firewall
2. Dashboard not running
3. Wrong IP address

**Solution:**
```bash
# 1. Verify container is running
ssh root@injective-devnet-2 "docker compose ps"

# 2. Check firewall (on server)
ssh root@injective-devnet-2 "iptables -L -n | grep 8000"

# 3. Test from server itself
ssh root@injective-devnet-2 "curl -I http://localhost:8000"

# If works locally but not externally → Firewall issue
# → Contact DevOps
```

---

### **Problem: "Unauthorized" or login not working**

**Solution:**
```bash
# Check credentials in .env on server
ssh root@injective-devnet-2 "grep 'WEB_AUTH' /root/injective/injective-testnet-liquidity-bot/.env"

# Restart to reload .env
ssh root@injective-devnet-2 "cd /root/injective/injective-testnet-liquidity-bot && docker compose restart web"
```

---

## 📊 Monitor Dashboard Access

### **View access logs:**

```bash
# On server
docker compose logs web | grep "GET"

# Filter by IP
docker compose logs web | grep "192.168"

# Real-time monitoring
docker compose logs -f web
```

### **Check active connections:**

```bash
# On server
netstat -an | grep :8000 | grep ESTABLISHED
```

---

## 🔐 Security Checklist

If exposing dashboard publicly:

- [ ] Strong password in .env (>16 characters, mixed case, symbols)
- [ ] IP whitelist configured (if possible)
- [ ] HTTPS/SSL enabled (if using reverse proxy)
- [ ] Access logs monitored regularly
- [ ] Dashboard credentials not shared in plain text (use password manager)
- [ ] VPN access preferred over direct internet access
- [ ] Rate limiting configured (if available)
- [ ] Failed login attempts monitored

---

## 📞 Questions for DevOps

If you need help from DevOps, ask:

1. **What's the public IP of injective-devnet-2?**
2. **Can you open port 8000 (TCP) on the firewall?**
3. **Should we use IP whitelist? (provide our team IPs)**
4. **Do you have a reverse proxy setup we can use?**
5. **Can we get a custom domain for the dashboard?**
6. **Is HTTPS/SSL certificate available?**
7. **Should we use VPN for access instead?**
8. **What's your preferred security approach for team dashboards?**

---

## ✅ Quick Reference

| Access Method | URL | Security | Setup Time | Team Access |
|---------------|-----|----------|------------|-------------|
| **SSH Tunnel** | `http://localhost:8000` | ⭐⭐⭐⭐⭐ | Immediate | No |
| **Public IP** | `http://203.0.113.45:8000` | ⭐⭐⭐ | Hours-Days | Yes |
| **Reverse Proxy** | `https://trading-bot.company.com` | ⭐⭐⭐⭐⭐ | Days-Week | Yes |

---

## 🎬 Complete Example

**Scenario**: You just deployed to devnet-2 and want to access the dashboard.

```bash
# Step 1: Verify it's running on server
ssh root@injective-devnet-2 "docker compose ps"
# Output: trading-bot-web   Up

# Step 2: Test locally on server
ssh root@injective-devnet-2 "curl -I http://localhost:8000"
# Output: HTTP/1.1 200 OK

# Step 3: Create SSH tunnel (on your Mac)
ssh -L 8000:localhost:8000 root@injective-devnet-2 -N
# Keep this running

# Step 4: Access dashboard (on your Mac, new terminal)
open http://localhost:8000

# Step 5: Login
# Username: admin
# Password: (from server .env)

# Step 6: Test starting a bot
# - Select wallet from dropdown
# - Select market
# - Click "Start Bot"
# - Verify bot appears in running bots list

# Step 7: Check bot logs
ssh root@injective-devnet-2
docker ps | grep bot
docker logs <bot-container-name>
```

**Success!** 🎉 You're now managing bots via Docker dashboard on devnet-2!

