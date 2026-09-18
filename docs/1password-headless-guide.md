# 1Password + Windows Hello Headless SSH Runbook

This guide documents the architecture and step-by-step procedure for using **1Password with Windows Hello biometrics** across SSH to power remote, headless development environments (such as Intel NUCs or cloud VMs) with **zero private keys or secrets stored on the remote storage medium**.

---

## 1. Architecture Overview

```text
┌────────────────────────────────────────────────────────┐
│             LOCAL CLIENT (Surface Book / Windows)      │
│                                                        │
│  1Password Desktop App (v8+)                           │
│   ├── Private SSH Keys & Credentials (sealed in TPM)   │
│   ├── Biometric Gate: Windows Hello (Fingerprint / PIN)│
│   └── Named Pipe: \\.\pipe\openssh-ssh-agent           │
└───────────────────────────┬────────────────────────────┘
                            │
                            │  SSH Tunnel (ForwardAgent yes)
                            │  via Tailscale Mesh / LAN
                            ▼
┌────────────────────────────────────────────────────────┐
│             REMOTE HOST (NUC01 / Debian Headless)      │
│                                                        │
│  Terminal Session                                      │
│   ├── Environment: $SSH_AUTH_SOCK (forwarded socket)   │
│   ├── Git Operations: git push / commit signing        │
│   ├── 1Password CLI: op run (memory-only injection)    │
│   └── DISK STORAGE: ZERO private keys or secrets       │
└────────────────────────────────────────────────────────┘
```

### Security Guarantees:
1. **Zero Keys on Remote Storage:** No private SSH keys (`id_rsa`, `id_ed25519`) exist on the remote filesystem.
2. **Biometric Authorization:** Every Git commit signature or push challenge is forwarded over the tunnel and prompts for Windows Hello on the local screen.
3. **Theft Immunity:** If the physical remote machine is stolen or compromised, the attacker finds only an OS installation with zero credentials.

---

## 2. Client Setup (Windows Laptop)

### Step 1: Enable 1Password Developer Settings
1. Open **1Password for Windows**.
2. Go to **Settings** (`Ctrl + ,`) → **Developer**.
3. Enable **"Use the SSH agent"**.
4. Enable **"Integrate with 1Password CLI"**.
5. Set authorization preference (e.g., *Authorize once per session* or *Every time*).

### Step 2: Configure Windows OpenSSH Client
Edit `C:\Users\<user>\.ssh\config`:

```ssh-config
Host nuc01
    HostName 100.88.63.109             # Or Tailscale MagicDNS name
    User mstouffer
    IdentityFile ~/.ssh/id_ed25519     # Public key authorized on the remote host
    ForwardAgent yes
    IdentityAgent "\\.\pipe\openssh-ssh-agent"
```

> **Note on WSL:** If connecting from WSL rather than Windows PowerShell, point `IdentityAgent` to the 1Password relay socket or use npiperelay:
> ```ssh-config
> Host nuc01
>     ForwardAgent yes
>     IdentityAgent ~/.1password/agent.sock
> ```

---

## 3. Remote Host Setup (NUC / Debian)

### Step 1: Verify Agent Forwarding
SSH into the remote host:
```bash
ssh nuc01
```

Confirm that the SSH agent socket is alive:
```bash
echo "$SSH_AUTH_SOCK"
# Should output something like: /tmp/ssh-XXXXXX/agent.XXXXXX

ssh-add -l
# Lists the public keys managed by your 1Password vault on Windows!
```

### Step 2: Configure Git to Use the Forwarded Agent
Test connecting to GitHub from the remote host:
```bash
ssh -T git@github.com
```
*A Windows Hello prompt will pop up on your laptop.* Once approved, GitHub will greet you by username.

### Step 3: Configure Cryptographic Commit Signing (No Local Keys)
Configure Git on the remote host to sign commits using the forwarded SSH key:

```bash
# 1. Tell Git to use SSH for signing
git config --global gpg.format ssh

# 2. Set your public key (from 1Password) as the signing key
git config --global user.signingkey "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..."

# 3. Enable automatic signing on all commits
git config --global commit.gpgsign true
```

Whenever you run `git commit`, your laptop screen will prompt for fingerprint/PIN before the commit is written.

---

## 4. Injecting API Keys & Secrets into Process RAM (`op run`)

To avoid storing plaintext `.env` files with API keys, database credentials, or cloud secrets on the remote disk:

### Step 1: Use Secret References in Templates
Create a template file (e.g., `.env.template` or `secrets.env`):
```bash
# Reference format: op://<vault-name>/<item-name>/[section/]<field>
OPENAI_API_KEY="op://Personal/OpenAI/credential"
DATABASE_URL="op://Dev/Postgres/connection-string"
AWS_ACCESS_KEY_ID="op://Personal/AWS/access-key-id"
AWS_SECRET_ACCESS_KEY="op://Personal/AWS/secret-access-key"
```

### Step 2: Inject at Runtime
Run your application through `op run`:
```bash
# Python
op run --env-file=.env.template -- python main.py

# Node / Next.js
op run --env-file=.env.template -- npm run dev

# Docker Compose
op run --env-file=.env.template -- docker compose up -d
```

* **In-Memory Only:** Secrets are populated directly into the spawned process's RAM environment block.
* **Disk Safe:** When the process terminates, the secrets disappear. Nothing is ever written to swap or storage.

---

## 5. Unattended / Headless Tasks (1Password Service Accounts)

For cron jobs, automated scripts, or Docker containers that must run when your laptop is disconnected or closed:

1. In 1Password, create a **Service Account** scoped *only* to a dedicated `NUC-Dev` vault.
2. Store the service account token in a restricted environment variable or systemd service override:
   ```bash
   export OP_SERVICE_ACCOUNT_TOKEN="opsa_eyJ..."
   ```
3. The NUC can now resolve `op run` secret references independently, without access to your personal vault or primary master password.

---

## 6. Reproduction Checklist for New Devices

When spinning up a new remote development machine:
- [ ] Connect machine to **Tailscale** for private mesh networking.
- [ ] Add machine host block to client `~/.ssh/config` with `ForwardAgent yes` and `IdentityAgent "\\.\pipe\openssh-ssh-agent"`.
- [ ] Install `1password-cli` (`op`) via Mise (`mise use --global op@latest`).
- [ ] Verify `echo $SSH_AUTH_SOCK` and `ssh-add -l` over SSH.
- [ ] Configure `git config --global gpg.format ssh` and set `user.signingkey`.
- [ ] Use `op run --env-file=...` instead of saving plaintext `.env` files.
