# infra — the keelspec.com server

One Terraform stack: an SSH key, a firewall, and a single Hetzner Cloud server
that boots with Docker installed and hardened SSH.

## What it creates

| Resource | Detail | Cost |
|---|---|---|
| `hcloud_server` | `cx23`, 2 vCPU / 4 GB / 40 GB NVMe, Ubuntu 24.04, Falkenstein | €5.49/mo |
| Primary IPv4 | attached to the server | ~€0.60/mo |
| Backups | daily, 7 slots (`enable_backups = true`) | +20% ≈ €1.10/mo |
| `hcloud_firewall` | inbound 22 / 80 / 443 only | free |
| `hcloud_ssh_key` | your `~/.ssh/id_ed25519.pub` | free |

**≈ €7.20/month ex-VAT.** Set `enable_backups = false` to drop it to ≈ €6.10.

## Supplying the token

You need a Hetzner Cloud account and a **Read & Write** API token:
Cloud Console → your project → Security → API tokens → Generate.

Do not paste it into a chat or commit it. Either export it for the session:

```bash
export HCLOUD_TOKEN="…"          # bash
$env:HCLOUD_TOKEN = "…"          # powershell
```

…or write it to `terraform.tfvars`, which is gitignored:

```hcl
hcloud_token = "…"
```

Terraform reads `HCLOUD_TOKEN` automatically if you name the variable
`TF_VAR_hcloud_token`, so this is the least error-prone form:

```bash
export TF_VAR_hcloud_token="…"
```

## Running it

```bash
cd infra
terraform init
terraform plan          # read this before applying — it creates billable resources
terraform apply
```

`terraform output next_steps` prints what to do afterwards. `terraform destroy`
removes the server and stops the billing; Hetzner bills by the hour, so a
short-lived test costs cents.

## Choices worth revisiting

- **`ssh_allowed_ips` defaults to the whole internet.** Port 22 is open to
  everyone, protected by key-only auth and fail2ban. If you have a static IP,
  narrow it: `ssh_allowed_ips = ["203.0.113.4/32"]`.
- **`server_type`.** `cx23` is the cheapest plan with enough RAM. Rescaling to
  `cx33` later is a reboot, not a migration — but note Hetzner grows disks and
  never shrinks them, so a rescale up is one-way.
- **`location`.** `fsn1` is EU and cheapest. Use `ash`/`hil` if the audience is
  mostly US; the price is the same but data-protection posture changes.
- **DNS is not managed here.** keelspec.com is registered elsewhere, so the
  records in `terraform output dns_records` have to be created by hand. If you
  move the domain to Hetzner DNS, the `hetznerdns` provider can take that over
  too — it needs a separate API token.
