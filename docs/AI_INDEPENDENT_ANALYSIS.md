# Independent AI Analysis Mode

This update separates AI investment analysis from the platform internal scoring engine.

## What Changed

- AI prompts no longer include:
  - internal beacon scores
  - recommendation engine outputs
  - internal sentiment weighting
  - portfolio confidence scoring

- AI providers are instructed to:
  - independently analyze the stock
  - use their own financial and technical reasoning
  - evaluate macro conditions
  - provide BUY / HOLD / SELL independently
  - provide concise responses to reduce token costs

## Prompt Rules

The application should only send:
- stock ticker
- company name
- optional entry price
- current market price
- optional portfolio allocation

The application must NOT send:
- internal scores
- platform recommendations
- proprietary ranking metrics
- internal AI voting

## Example Minimal Prompt

Analyze stock: AAPL.

Provide:
- short-term outlook
- long-term outlook
- risk level
- technical trend
- valuation opinion
- BUY/HOLD/SELL

Keep response under 120 words.
