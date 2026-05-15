# Security policy

## Reporting

If you find a security issue, please report it privately to the maintainers (add contact when publishing the repository).

## Secrets

Never commit API keys, JWT secrets, or database passwords. Use environment variables and `.env` (gitignored).

## Production checklist

- Rotate `JWT_SECRET` and concentrator API keys.
- Run API behind TLS termination (reverse proxy).
- Restrict CORS origins in `beeplan.config.Settings.cors_origins`.
