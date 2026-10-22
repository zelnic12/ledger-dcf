# Ledger DCF

A discounted cash flow calculator. Type a ticker (or a company name) and it pulls live prices and financial statements from Yahoo Finance, then values the company from its free cash flow.

## Run it

Requires Python 3.9+ and nothing else (no packages, no API key).

```bash
python server.py
```

Then open http://localhost:8765. On Windows you can double-click `start.bat` instead.

## What it does

- **Search** by ticker or company name with live suggestions. Works for international listings (`7203.T`, `SHEL.L`, `TSM`).
- **Valuation summary**: intrinsic value per share vs. market price, an undervalued / fair / overvalued verdict and margin of safety.
- **Adjustable assumptions**
  - Base free cash flow: latest year, 3-year average or a custom figure
  - Growth for years 1–5, fading to terminal growth over years 6–10
  - WACC from CAPM: live US 10-year Treasury yield, a 5-year monthly beta calculated against the home-market index, equity risk premium, cost of debt and effective tax rate
- **Outputs**: FCF history and forecast chart, enterprise value to equity bridge, 10-year projection table, and a WACC × terminal growth sensitivity grid.
- Light and dark themes; works on phones.

## How the model works

1. FCF = operating cash flow − capital expenditure.
2. FCF grows at the stage-one rate for 5 years, then fades linearly to terminal growth by year 10.
3. Terminal value = FCF₁₀ × (1 + g) / (WACC − g).
4. Enterprise value = PV of years 1–10 + PV of terminal value.
5. Equity value = EV + cash − debt − minority interest, divided by shares outstanding.

## Limitations

- Banks, insurers and companies with large finance arms don't suit an FCF model.
- For companies that report in a different currency from the one they trade in (ADRs such as TSM), enter the number of ordinary shares per ADR.
- The risk-free rate defaults to the US 10-year yield for every company; edit it for other markets.
- Data comes from Yahoo Finance's unofficial public endpoints, which may change or rate-limit.

This is a calculator, not investment advice.
