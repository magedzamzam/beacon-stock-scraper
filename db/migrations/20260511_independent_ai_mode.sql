-- Independent AI mode configuration

CREATE TABLE IF NOT EXISTS ai_provider_settings (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(50) NOT NULL,
    api_key TEXT,
    enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_prompt_templates (
    id SERIAL PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    prompt_body TEXT NOT NULL,
    minimized BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
