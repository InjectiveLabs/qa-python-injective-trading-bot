# Questions for DevOps - Docker Deployment

## 📋 Context

We're preparing to dockerize our trading bot system as you suggested with Docker Compose. The system consists of:
- A web dashboard for monitoring and control
- Multiple trading bots that are started/stopped dynamically by users
- Persistent logs and configuration files
- Sensitive data (wallet private keys)

Before implementation, we need to align on infrastructure and architecture decisions to ensure we follow your standards and practices.

**Architecture diagram**: See `DOCKER_ARCHITECTURE.md` in this folder

---

## 🎯 Critical Questions (Must Answer)

### 1. Infrastructure & Environment

**Q1: What infrastructure will this run on?**
- [ ] Existing Docker host (which one?)
- [ ] New dedicated server
- [ ] VM (specs?)
- [ ] Cloud instance (AWS/GCP/Azure?)

**Q2: Docker environment details:**
- What Docker version is installed?
- What Docker Compose version?
- Any custom Docker daemon configurations we should know about?

**Q3: Network access to the dashboard:**
- [ ] You'll set up reverse proxy (nginx/traefik/other)?
- [ ] You'll handle SSL/TLS certificates?
- [ ] Domain name available: ________________
- [ ] Or just IP:port access?
- [ ] VPN required or public internet?

---

### 2. Architecture Validation

**⚠️ Q4: Docker Socket Access (CRITICAL)**

Our web dashboard needs access to Docker socket (`/var/run/docker.sock`) to dynamically create and manage bot containers.

**This gives the web container full Docker control.**

Options:
- [ ] **Option A**: Mount docker socket directly (simple, less secure)
- [ ] **Option B**: Use docker-socket-proxy to restrict API access (more secure)
- [ ] **Option C**: Pre-define all bot combinations in docker-compose.yml (no socket access needed, less flexible)

**Which approach do you prefer?**

**Security context**: Dashboard is protected by HTTP basic auth. Only authorized users can access.

---

**Q5: Dynamic Container Creation**

Our design creates bot containers dynamically when users click "Start Bot" in the UI. This means:
- ✅ Flexible - users pick any wallet+market combination
- ❌ Containers won't appear in `docker-compose.yml`
- ❌ `docker compose ps` won't show them (need `docker ps --filter label=app=trading-bot`)

Alternative: Pre-define all possible bot combinations in docker-compose.yml (10-20 services)

**Is dynamic container creation acceptable?**
- [ ] Yes, dynamic is fine
- [ ] No, prefer pre-defined in docker-compose.yml

---

**Q6: Network Configuration**

Current plan: All containers on Docker bridge network, communicating internally.

**Requirements:**
- Outbound HTTPS access to:
  - sentry.injective.network (testnet API)
  - sentry.injective.network (mainnet API for prices)
- Only web dashboard (port 8000) needs inbound access

**Questions:**
- Any firewall rules we need to request?
- Corporate proxy configuration needed?
- Network segmentation requirements?

---

### 3. Data Persistence & Storage

**Q7: How should we handle persistent volumes?**

**Option A: Bind Mounts** (simple, direct filesystem access)
```yaml
volumes:
  - /var/trading-bot/logs:/app/logs
  - /var/trading-bot/config:/app/config
```
- Pros: Easy to access files directly on host
- Cons: Need to manage host directory permissions

**Option B: Named Volumes** (Docker-managed)
```yaml
volumes:
  - trading-logs:/app/logs
  - trading-config:/app/config
```
- Pros: Docker handles management
- Cons: Files not easily accessible on host

**Which do you prefer?** _________________

**Where should data be stored?** (if bind mounts)
- Logs: `/var/trading-bot/logs` or _________________
- Config: `/var/trading-bot/config` or _________________

---

**Q8: Log Management**

- Current plan: 5-day log retention, managed by application
- Log files written by multiple containers to shared volume

**Questions:**
- Do you have centralized logging (ELK, Datadog, Splunk)?
- Should we send logs there instead of/in addition to files?
- Log rotation policies to follow?
- Disk space available for logs?

---

### 4. Secrets Management

**⚠️ Q9: Wallet Private Keys & Credentials (CRITICAL)**

We have sensitive data:
- Wallet private keys (3-6 wallets, may grow)
- Dashboard username/password

Currently stored in `.env` file (git-ignored).

**Your preferred approach:**
- [ ] **Option A**: `.env` file on server (you manage it)
- [ ] **Option B**: Docker secrets (`docker secret create`)
- [ ] **Option C**: External secrets manager (AWS Secrets Manager, Vault, etc.)
- [ ] **Option D**: Your existing secrets solution: _________________

**If Option A (.env file):**
- Who creates and maintains the .env file on server?
- How are secrets rotated if needed?

---

### 5. Deployment & CI/CD

**Q10: Deployment method**

**Option A: Manual** (simple)
```bash
git pull
docker-compose build
docker-compose up -d
```

**Option B: CI/CD Pipeline** (automated)
- GitHub Actions / GitLab CI / Jenkins?
- Triggered by: git push to main? Manual trigger?

**Option C: You handle deployment** (we just provide files)

**Which approach do you prefer?** _________________

---

**Q11: Container Registry**

Should we:
- [ ] Build images directly on server (slower, no registry needed)
- [ ] Push to Docker Hub (public, easy)
- [ ] Push to private registry (which one? _________________)
- [ ] Push to cloud registry (ECR/GCR/ACR?)

**If registry: who manages it and push permissions?**

---

**Q12: Update Process**

When we deploy code updates:
- Is it acceptable to restart all bots for ~30 seconds?
- Or need zero-downtime updates (more complex)?

**Current plan:**
- Web dashboard restarts (30 sec downtime)
- Running bots continue uninterrupted
- Only bots started after update use new code

**Is this acceptable?** _________________

---

### 6. Monitoring & Operations

**Q13: Monitoring Infrastructure**

Do you have monitoring tools we should integrate with?
- [ ] Prometheus/Grafana
- [ ] Datadog
- [ ] CloudWatch / Stackdriver
- [ ] Other: _________________
- [ ] None (just Docker logs)

**If yes: Should we expose metrics endpoints?** (e.g., `/metrics` for Prometheus)

---

**Q14: Restart Policies**

Our plan:
- Web dashboard: `restart: unless-stopped` (always running)
- Bot containers: `restart: unless-stopped` (auto-restart on crash, but not if user stops)

**Acceptable?** Or different policy preferred?

---

**Q15: Resource Limits**

Should we set CPU/memory limits?

**Estimated usage:**
- Web dashboard: 256MB RAM, 0.5 CPU
- Each bot: 128MB RAM, 0.25 CPU
- Total (3 bots running): ~1GB RAM, 1.5 CPU

**Should we add limits like:**
```yaml
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 256M
```

**Your preference:** _________________

---

### 7. Security & Compliance

**Q16: Security Requirements**

- Container image scanning required?
- Vulnerability scanning tools?
- Compliance frameworks (SOC2, PCI, etc.)?
- Security policies we should follow?

---

**Q17: Access Control**

- Who should have SSH/access to the Docker host?
- Who can deploy updates?
- Audit logging requirements?

---

### 8. Timeline & Next Steps

**Q18: Timeline**
- When do you need this deployed?
- Any maintenance windows coming up?
- Time for proof-of-concept/testing?

---

**Q19: Review Process**
- Should we schedule a call to discuss? (30 min)
- Or async review is fine?
- Who should be included in discussions?

---

**Q20: Documentation Needs**
What documentation do you need from us?
- [ ] Deployment guide
- [ ] Troubleshooting runbook
- [ ] Architecture diagrams (see DOCKER_ARCHITECTURE.md)
- [ ] Backup/recovery procedures
- [ ] Other: _________________

---

## 📊 Summary of Our Proposal

**What we're building:**
- 1 web dashboard container (always running)
- N bot containers (created dynamically by users)
- Shared volumes for logs and config
- Docker Compose for orchestration

**Key characteristics:**
- Simple architecture (no database, no message queues)
- Suitable for 3-10 concurrent bots
- Designed for single-server deployment
- Manual scaling (add more bots via UI)

**What we need from you:**
- Server/infrastructure
- Network access configuration
- Secrets management approach
- Deployment method preference
- Reverse proxy & SSL setup (if needed)

---

## ⏭️ Next Steps

1. **Your review** of architecture (see DOCKER_ARCHITECTURE.md)
2. **Answers** to critical questions above
3. **Discussion** (call or async) to finalize approach
4. **Implementation** based on your requirements
5. **Testing** on provided infrastructure
6. **Deployment** and handoff

**Estimated timeline after alignment: 3-5 days for implementation + testing**

---

## 📞 Contact

Please respond with answers or let us know if you'd like to schedule a call to discuss.

**Priority questions**: Q4, Q5, Q7, Q9, Q10, Q11

Thank you!
