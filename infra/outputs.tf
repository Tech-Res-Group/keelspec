output "ipv4" {
  description = "Server IPv4 — the A record for keelspec.com and www."
  value       = hcloud_server.web.ipv4_address
}

output "ipv6" {
  description = "Server IPv6 — the AAAA record."
  value       = hcloud_server.web.ipv6_address
}

output "ssh" {
  description = "Log in."
  value       = "ssh ${var.deploy_user}@${hcloud_server.web.ipv4_address}"
}

output "dns_records" {
  description = "Create these at your registrar before the first deploy, or Caddy cannot get a certificate."
  value = <<-EOT
    keelspec.com.       A     ${hcloud_server.web.ipv4_address}
    keelspec.com.       AAAA  ${hcloud_server.web.ipv6_address}
    www.keelspec.com.   A     ${hcloud_server.web.ipv4_address}
    www.keelspec.com.   AAAA  ${hcloud_server.web.ipv6_address}
  EOT
}

output "next_steps" {
  value = <<-EOT

    1. Create the DNS records above and wait for them to resolve:
         nslookup keelspec.com

    2. Push the site (from site/):
         KEELSPEC_HOST=${var.deploy_user}@${hcloud_server.web.ipv4_address} ./deploy.sh

    3. On the server, once:
         cd ${var.remote_dir}
         cp .env.example .env && chmod 600 .env
         # set ACME_EMAIL, and generate:
         #   openssl rand -hex 32  -> ADMIN_TOKEN
         #   openssl rand -hex 16  -> IP_SALT
         docker compose up -d
         docker compose logs -f caddy

    Note: cloud-init takes 2-3 minutes after boot. If ssh refuses the deploy
    user at first, wait and retry.
  EOT
}
