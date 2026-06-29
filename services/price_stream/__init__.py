"""price_stream — Capital.com WebSocket streaming service (mainly Gold).

Connects to Capital.com's streaming API, subscribes to OHLC candles and
bid/offer quotes for a configured set of epics (default: GOLD), and persists
them to `intraday_bar` / `stream_quote`. The API's move-signal then reads the
streamed bars and runs the same scorer used for daily stocks.

Auth is brokered through broker_gateway (the only service that may decrypt
broker credentials): we ask it for a streaming session (CST + security token)
and use those on the socket.
"""
