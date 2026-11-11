# Security

- Secrets (API keys, the bot token) come only from environment variables. `config.toml` names the variable, never the value.
- An API key is sent only over https, or to a server on your own machine. Redirects are never followed, so a key cannot be passed on to another host.
- Speech models load as safetensors weights, with no remote code. Use model ids you trust.
- Recordings stay on your machine. The transcript text goes to the LLM endpoint you configure, and the update file goes to your publish targets. With a local LLM, nothing leaves your machine except what you publish.
- A transcript is untrusted text. Someone in a meeting could say "ignore your instructions". The worst result is a wrong update file, so read it before you publish.

To report a security problem, open a GitHub issue without the details and ask for a private contact.
