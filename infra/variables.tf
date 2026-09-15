variable "hcloud_token" {
  description = "Hetzner Cloud API token (Read & Write). Prefer the HCLOUD_TOKEN env var over putting it in a file."
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Name for the server and its related resources."
  type        = string
  default     = "keelspec"
}

variable "server_type" {
  description = "Hetzner server type. cx23 = 2 vCPU / 4 GB / 40 GB, EUR 5.49/mo ex-VAT. Verify with: hcloud server-type list"
  type        = string
  default     = "cx23"
}

variable "location" {
  description = "fsn1 Falkenstein, nbg1 Nuremberg, hel1 Helsinki (all EU); ash Ashburn, hil Hillsboro (US); sin Singapore."
  type        = string
  default     = "fsn1"
}

variable "image" {
  description = "Base OS image."
  type        = string
  default     = "ubuntu-24.04"
}

variable "ssh_public_key_path" {
  description = "Public key uploaded to the server for the deploy user."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_allowed_ips" {
  description = "CIDRs allowed to reach port 22. Narrow this to your own IP once you have one that is stable."
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}

variable "deploy_user" {
  description = "Unprivileged user that owns the site and runs docker."
  type        = string
  default     = "deploy"
}

variable "remote_dir" {
  description = "Where the compose project lives on the server. Must match REMOTE_DIR in deploy.sh."
  type        = string
  default     = "/opt/keelspec-site"
}

variable "enable_backups" {
  description = "Hetzner automatic backups, +20% of the server price."
  type        = bool
  default     = true
}
