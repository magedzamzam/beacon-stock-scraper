--
-- PostgreSQL database dump
--

\restrict 7jpAa23pHdYRH6H4l6DnTM8rQiQ2nyvGqgrz6SPo37BkrxfDSSquIIjfu2OFR1B

-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.2

-- Started on 2026-05-07 19:01:36

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 222 (class 1259 OID 16402)
-- Name: exchanges; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.exchanges (
    id integer NOT NULL,
    code character varying(10) NOT NULL,
    name character varying(100) NOT NULL,
    country character varying(100)
);


ALTER TABLE public.exchanges OWNER TO magedzamzam;

--
-- TOC entry 221 (class 1259 OID 16401)
-- Name: exchanges_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.exchanges_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.exchanges_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4557 (class 0 OID 0)
-- Dependencies: 221
-- Name: exchanges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.exchanges_id_seq OWNED BY public.exchanges.id;


--
-- TOC entry 250 (class 1259 OID 16838)
-- Name: portfolio_positions; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.portfolio_positions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    stock_id bigint NOT NULL,
    quantity numeric(20,6) NOT NULL,
    avg_entry_price numeric(18,6) NOT NULL,
    entry_date date,
    notes text,
    is_open boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    CONSTRAINT portfolio_positions_avg_entry_price_check CHECK ((avg_entry_price > (0)::numeric)),
    CONSTRAINT portfolio_positions_quantity_check CHECK ((quantity > (0)::numeric))
);


ALTER TABLE public.portfolio_positions OWNER TO magedzamzam;

--
-- TOC entry 249 (class 1259 OID 16837)
-- Name: portfolio_positions_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.portfolio_positions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.portfolio_positions_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4558 (class 0 OID 0)
-- Dependencies: 249
-- Name: portfolio_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.portfolio_positions_id_seq OWNED BY public.portfolio_positions.id;


--
-- TOC entry 252 (class 1259 OID 16863)
-- Name: portfolio_trades; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.portfolio_trades (
    id bigint NOT NULL,
    position_id bigint NOT NULL,
    trade_type character varying(8) NOT NULL,
    quantity numeric(20,6) NOT NULL,
    price numeric(18,6) NOT NULL,
    trade_date date NOT NULL,
    fees numeric(18,6) DEFAULT 0,
    notes text,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT portfolio_trades_trade_type_check CHECK (((trade_type)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying])::text[])))
);


ALTER TABLE public.portfolio_trades OWNER TO magedzamzam;

--
-- TOC entry 251 (class 1259 OID 16862)
-- Name: portfolio_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.portfolio_trades_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.portfolio_trades_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4559 (class 0 OID 0)
-- Dependencies: 251
-- Name: portfolio_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.portfolio_trades_id_seq OWNED BY public.portfolio_trades.id;


--
-- TOC entry 256 (class 1259 OID 16901)
-- Name: position_recommendations; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.position_recommendations (
    id bigint NOT NULL,
    position_id bigint NOT NULL,
    score_date date NOT NULL,
    current_price numeric(18,6),
    unrealized_pl_pct numeric(12,4),
    verdict character varying(16) NOT NULL,
    confidence numeric(5,2),
    reasoning jsonb,
    scraped_at timestamp without time zone DEFAULT now(),
    CONSTRAINT position_recommendations_verdict_check CHECK (((verdict)::text = ANY ((ARRAY['HOLD'::character varying, 'SELL'::character varying, 'BUY_MORE'::character varying, 'TRIM'::character varying, 'STOP_LOSS'::character varying])::text[])))
);


ALTER TABLE public.position_recommendations OWNER TO magedzamzam;

--
-- TOC entry 255 (class 1259 OID 16900)
-- Name: position_recommendations_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.position_recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.position_recommendations_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4560 (class 0 OID 0)
-- Dependencies: 255
-- Name: position_recommendations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.position_recommendations_id_seq OWNED BY public.position_recommendations.id;


--
-- TOC entry 240 (class 1259 OID 16543)
-- Name: scrape_runs; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.scrape_runs (
    id bigint NOT NULL,
    stock_id bigint,
    source character varying(64) NOT NULL,
    run_time timestamp without time zone DEFAULT now(),
    status character varying(16),
    http_status integer,
    error_message text
);


ALTER TABLE public.scrape_runs OWNER TO magedzamzam;

--
-- TOC entry 239 (class 1259 OID 16542)
-- Name: scrape_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.scrape_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scrape_runs_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4561 (class 0 OID 0)
-- Dependencies: 239
-- Name: scrape_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.scrape_runs_id_seq OWNED BY public.scrape_runs.id;


--
-- TOC entry 234 (class 1259 OID 16492)
-- Name: stock_analyst_consensus; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_analyst_consensus (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    consensus_date date NOT NULL,
    analyst_count integer,
    rating character varying(32),
    target_price numeric(18,6),
    implied_upside_pct numeric(12,6),
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_analyst_consensus OWNER TO magedzamzam;

--
-- TOC entry 233 (class 1259 OID 16491)
-- Name: stock_analyst_consensus_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_analyst_consensus_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_analyst_consensus_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4562 (class 0 OID 0)
-- Dependencies: 233
-- Name: stock_analyst_consensus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_analyst_consensus_id_seq OWNED BY public.stock_analyst_consensus.id;


--
-- TOC entry 262 (class 1259 OID 16952)
-- Name: stock_corporate_actions; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_corporate_actions (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    action_date date NOT NULL,
    action_type character varying(32) NOT NULL,
    details jsonb,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_corporate_actions OWNER TO magedzamzam;

--
-- TOC entry 261 (class 1259 OID 16951)
-- Name: stock_corporate_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_corporate_actions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_corporate_actions_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4563 (class 0 OID 0)
-- Dependencies: 261
-- Name: stock_corporate_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_corporate_actions_id_seq OWNED BY public.stock_corporate_actions.id;


--
-- TOC entry 260 (class 1259 OID 16934)
-- Name: stock_disclosures; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_disclosures (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    disclosure_date date,
    disclosure_type character varying(64),
    title text NOT NULL,
    summary text,
    sentiment_score numeric(5,2),
    importance character varying(16),
    source character varying(64),
    url text,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_disclosures OWNER TO magedzamzam;

--
-- TOC entry 259 (class 1259 OID 16933)
-- Name: stock_disclosures_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_disclosures_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_disclosures_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4564 (class 0 OID 0)
-- Dependencies: 259
-- Name: stock_disclosures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_disclosures_id_seq OWNED BY public.stock_disclosures.id;


--
-- TOC entry 238 (class 1259 OID 16526)
-- Name: stock_etf_holders; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_etf_holders (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    etf_name text NOT NULL,
    weight_pct numeric(12,6),
    aum numeric(24,4),
    currency character varying(10),
    source_date date,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_etf_holders OWNER TO magedzamzam;

--
-- TOC entry 237 (class 1259 OID 16525)
-- Name: stock_etf_holders_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_etf_holders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_etf_holders_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4565 (class 0 OID 0)
-- Dependencies: 237
-- Name: stock_etf_holders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_etf_holders_id_seq OWNED BY public.stock_etf_holders.id;


--
-- TOC entry 232 (class 1259 OID 16476)
-- Name: stock_financials; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_financials (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    fiscal_year integer NOT NULL,
    period_type character varying(16) NOT NULL,
    statement_type character varying(16) NOT NULL,
    revenue numeric(24,4),
    net_income numeric(24,4),
    ebitda numeric(24,4),
    operating_income numeric(24,4),
    total_assets numeric(24,4),
    total_equity numeric(24,4),
    total_debt numeric(24,4),
    cash_and_equivalents numeric(24,4),
    operating_cash_flow numeric(24,4),
    free_cash_flow numeric(24,4),
    is_estimate boolean DEFAULT false,
    source_date date,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_financials OWNER TO magedzamzam;

--
-- TOC entry 231 (class 1259 OID 16475)
-- Name: stock_financials_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_financials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_financials_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4566 (class 0 OID 0)
-- Dependencies: 231
-- Name: stock_financials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_financials_id_seq OWNED BY public.stock_financials.id;


--
-- TOC entry 263 (class 1259 OID 16968)
-- Name: stock_latest_snapshot; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_latest_snapshot (
    stock_id bigint NOT NULL,
    last_close numeric(18,6),
    last_change_pct numeric(12,6),
    market_cap numeric(24,4),
    pe_ratio numeric(18,6),
    dividend_yield_pct numeric(12,6),
    week_52_high numeric(18,6),
    week_52_low numeric(18,6),
    rsi_14 numeric(10,4),
    analyst_target numeric(18,6),
    analyst_upside_pct numeric(12,6),
    composite_score numeric(6,2),
    verdict character varying(16),
    last_updated timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_latest_snapshot OWNER TO magedzamzam;

--
-- TOC entry 236 (class 1259 OID 16507)
-- Name: stock_management; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_management (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    person_name text NOT NULL,
    title text,
    start_date date,
    is_board_member boolean DEFAULT false,
    is_executive boolean DEFAULT true,
    active boolean DEFAULT true
);


ALTER TABLE public.stock_management OWNER TO magedzamzam;

--
-- TOC entry 235 (class 1259 OID 16506)
-- Name: stock_management_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_management_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_management_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4567 (class 0 OID 0)
-- Dependencies: 235
-- Name: stock_management_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_management_id_seq OWNED BY public.stock_management.id;


--
-- TOC entry 226 (class 1259 OID 16430)
-- Name: stock_market_daily; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_market_daily (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    trading_date date NOT NULL,
    close_price numeric(18,6),
    open_price numeric(18,6),
    high_price numeric(18,6),
    low_price numeric(18,6),
    volume bigint,
    market_cap numeric(24,4),
    free_float_pct numeric(8,4),
    beta numeric(12,6),
    pe_ratio numeric(18,6),
    forward_pe numeric(18,6),
    dividend numeric(18,6),
    dividend_yield_pct numeric(12,6),
    week_52_low numeric(18,6),
    week_52_high numeric(18,6),
    scraped_at timestamp without time zone DEFAULT now(),
    enterprise_value numeric(24,4),
    revenue_ttm numeric(24,4),
    dividend_growth_pct numeric(12,6),
    ex_dividend_date date,
    payout_ratio_pct numeric(12,6),
    payout_frequency character varying(32),
    week_52_low_change_pct numeric(12,6),
    week_52_high_change_pct numeric(12,6)
);


ALTER TABLE public.stock_market_daily OWNER TO magedzamzam;

--
-- TOC entry 4568 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.revenue_ttm; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.revenue_ttm IS 'Revenue metric from ListOfCompanies CSV snapshot; fiscal-year context is not supplied.';


--
-- TOC entry 4569 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.dividend_growth_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.dividend_growth_pct IS 'Dividend growth percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4570 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.ex_dividend_date; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.ex_dividend_date IS 'Ex-dividend date from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4571 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.payout_ratio_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.payout_ratio_pct IS 'Payout ratio percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4572 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.payout_frequency; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.payout_frequency IS 'Payout frequency from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4573 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.week_52_low_change_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.week_52_low_change_pct IS 'Current price change from 52-week low, as displayed in ListOfCompanies CSV snapshot.';


--
-- TOC entry 4574 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.week_52_high_change_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.week_52_high_change_pct IS 'Current price change from 52-week high, as displayed in ListOfCompanies CSV snapshot.';


--
-- TOC entry 225 (class 1259 OID 16429)
-- Name: stock_market_daily_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_market_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_market_daily_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4575 (class 0 OID 0)
-- Dependencies: 225
-- Name: stock_market_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_market_daily_id_seq OWNED BY public.stock_market_daily.id;


--
-- TOC entry 242 (class 1259 OID 16632)
-- Name: stock_news; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_news (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    news_date date,
    headline text NOT NULL,
    source_code character varying(32),
    url text,
    scraped_at timestamp without time zone DEFAULT now(),
    summary text,
    sentiment_score numeric(5,2),
    sentiment_label character varying(16)
);


ALTER TABLE public.stock_news OWNER TO magedzamzam;

--
-- TOC entry 241 (class 1259 OID 16631)
-- Name: stock_news_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_news_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_news_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4576 (class 0 OID 0)
-- Dependencies: 241
-- Name: stock_news_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_news_id_seq OWNED BY public.stock_news.id;


--
-- TOC entry 228 (class 1259 OID 16446)
-- Name: stock_performance_daily; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_performance_daily (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    trading_date date NOT NULL,
    return_1d numeric(12,6),
    return_1w numeric(12,6),
    return_1m numeric(12,6),
    return_3m numeric(12,6),
    return_6m numeric(12,6),
    return_ytd numeric(12,6),
    return_1y numeric(12,6),
    scraped_at timestamp without time zone DEFAULT now(),
    return_5y numeric(12,6),
    return_10y numeric(12,6)
);


ALTER TABLE public.stock_performance_daily OWNER TO magedzamzam;

--
-- TOC entry 4577 (class 0 OID 0)
-- Dependencies: 228
-- Name: COLUMN stock_performance_daily.return_5y; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_performance_daily.return_5y IS 'Five-year return percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4578 (class 0 OID 0)
-- Dependencies: 228
-- Name: COLUMN stock_performance_daily.return_10y; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_performance_daily.return_10y IS 'Ten-year return percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 227 (class 1259 OID 16445)
-- Name: stock_performance_daily_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_performance_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_performance_daily_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4579 (class 0 OID 0)
-- Dependencies: 227
-- Name: stock_performance_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_performance_daily_id_seq OWNED BY public.stock_performance_daily.id;


--
-- TOC entry 254 (class 1259 OID 16880)
-- Name: stock_recommendations; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_recommendations (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    score_date date NOT NULL,
    fundamental_score numeric(6,2),
    valuation_score numeric(6,2),
    momentum_score numeric(6,2),
    technical_score numeric(6,2),
    analyst_score numeric(6,2),
    quality_score numeric(6,2),
    risk_score numeric(6,2),
    composite_score numeric(6,2),
    verdict character varying(16) NOT NULL,
    reasoning jsonb,
    model_version character varying(32) DEFAULT 'v1'::character varying,
    scraped_at timestamp without time zone DEFAULT now(),
    CONSTRAINT stock_recommendations_verdict_check CHECK (((verdict)::text = ANY ((ARRAY['BUY'::character varying, 'WATCH'::character varying, 'STAY_AWAY'::character varying])::text[])))
);


ALTER TABLE public.stock_recommendations OWNER TO magedzamzam;

--
-- TOC entry 253 (class 1259 OID 16879)
-- Name: stock_recommendations_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_recommendations_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4580 (class 0 OID 0)
-- Dependencies: 253
-- Name: stock_recommendations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_recommendations_id_seq OWNED BY public.stock_recommendations.id;


--
-- TOC entry 258 (class 1259 OID 16919)
-- Name: stock_technicals; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_technicals (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    trading_date date NOT NULL,
    rsi_14 numeric(10,4),
    sma_50 numeric(18,6),
    sma_200 numeric(18,6),
    ema_20 numeric(18,6),
    macd numeric(18,6),
    macd_signal numeric(18,6),
    atr_14 numeric(18,6),
    volatility_30d numeric(12,6),
    above_sma_50 boolean,
    above_sma_200 boolean,
    golden_cross boolean,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_technicals OWNER TO magedzamzam;

--
-- TOC entry 257 (class 1259 OID 16918)
-- Name: stock_technicals_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_technicals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_technicals_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4581 (class 0 OID 0)
-- Dependencies: 257
-- Name: stock_technicals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_technicals_id_seq OWNED BY public.stock_technicals.id;


--
-- TOC entry 230 (class 1259 OID 16461)
-- Name: stock_valuation; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stock_valuation (
    id bigint NOT NULL,
    stock_id bigint NOT NULL,
    fiscal_year integer NOT NULL,
    pe numeric(18,6),
    ev_sales numeric(18,6),
    ev_ebitda numeric(18,6),
    price_to_book numeric(18,6),
    dividend_yield_pct numeric(12,6),
    source_date date,
    scraped_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.stock_valuation OWNER TO magedzamzam;

--
-- TOC entry 229 (class 1259 OID 16460)
-- Name: stock_valuation_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stock_valuation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_valuation_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4582 (class 0 OID 0)
-- Dependencies: 229
-- Name: stock_valuation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stock_valuation_id_seq OWNED BY public.stock_valuation.id;


--
-- TOC entry 224 (class 1259 OID 16411)
-- Name: stocks; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.stocks (
    id bigint NOT NULL,
    exchange_id integer,
    ticker character varying(32),
    isin character varying(32),
    marketscreener_slug text,
    company_name text NOT NULL,
    sector text,
    industry text,
    currency character varying(10),
    founded_year integer,
    employees integer,
    website text,
    active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    country text
);


ALTER TABLE public.stocks OWNER TO magedzamzam;

--
-- TOC entry 4583 (class 0 OID 0)
-- Dependencies: 224
-- Name: COLUMN stocks.country; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stocks.country IS 'Company country from ListOfCompanies CSV files.';


--
-- TOC entry 223 (class 1259 OID 16410)
-- Name: stocks_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.stocks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stocks_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4584 (class 0 OID 0)
-- Dependencies: 223
-- Name: stocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stocks_id_seq OWNED BY public.stocks.id;


--
-- TOC entry 244 (class 1259 OID 16787)
-- Name: users; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    display_name character varying(120),
    password_hash character varying(255) NOT NULL,
    is_admin boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now(),
    last_login_at timestamp without time zone
);


ALTER TABLE public.users OWNER TO magedzamzam;

--
-- TOC entry 243 (class 1259 OID 16786)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4585 (class 0 OID 0)
-- Dependencies: 243
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- TOC entry 264 (class 1259 OID 16979)
-- Name: v_stock_overview; Type: VIEW; Schema: public; Owner: magedzamzam
--

CREATE VIEW public.v_stock_overview AS
 SELECT s.id AS stock_id,
    s.ticker,
    s.company_name,
    s.sector,
    s.industry,
    s.country,
    s.currency,
    e.code AS exchange_code,
    e.name AS exchange_name,
    snap.last_close,
    snap.last_change_pct,
    snap.market_cap,
    snap.pe_ratio,
    snap.dividend_yield_pct,
    snap.composite_score,
    snap.verdict,
    snap.last_updated
   FROM ((public.stocks s
     JOIN public.exchanges e ON ((e.id = s.exchange_id)))
     LEFT JOIN public.stock_latest_snapshot snap ON ((snap.stock_id = s.id)))
  WHERE (s.active IS TRUE);


ALTER VIEW public.v_stock_overview OWNER TO magedzamzam;

--
-- TOC entry 248 (class 1259 OID 16816)
-- Name: watchlist_items; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.watchlist_items (
    id bigint NOT NULL,
    watchlist_id bigint NOT NULL,
    stock_id bigint NOT NULL,
    note text,
    added_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.watchlist_items OWNER TO magedzamzam;

--
-- TOC entry 247 (class 1259 OID 16815)
-- Name: watchlist_items_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.watchlist_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.watchlist_items_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4586 (class 0 OID 0)
-- Dependencies: 247
-- Name: watchlist_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.watchlist_items_id_seq OWNED BY public.watchlist_items.id;


--
-- TOC entry 246 (class 1259 OID 16800)
-- Name: watchlists; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.watchlists (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    name character varying(120) DEFAULT 'Default'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.watchlists OWNER TO magedzamzam;

--
-- TOC entry 245 (class 1259 OID 16799)
-- Name: watchlists_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.watchlists_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.watchlists_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4587 (class 0 OID 0)
-- Dependencies: 245
-- Name: watchlists_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.watchlists_id_seq OWNED BY public.watchlists.id;


--
-- TOC entry 4240 (class 2604 OID 16405)
-- Name: exchanges id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges ALTER COLUMN id SET DEFAULT nextval('public.exchanges_id_seq'::regclass);


--
-- TOC entry 4274 (class 2604 OID 16841)
-- Name: portfolio_positions id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions ALTER COLUMN id SET DEFAULT nextval('public.portfolio_positions_id_seq'::regclass);


--
-- TOC entry 4278 (class 2604 OID 16866)
-- Name: portfolio_trades id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades ALTER COLUMN id SET DEFAULT nextval('public.portfolio_trades_id_seq'::regclass);


--
-- TOC entry 4284 (class 2604 OID 16904)
-- Name: position_recommendations id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations ALTER COLUMN id SET DEFAULT nextval('public.position_recommendations_id_seq'::regclass);


--
-- TOC entry 4262 (class 2604 OID 16546)
-- Name: scrape_runs id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs ALTER COLUMN id SET DEFAULT nextval('public.scrape_runs_id_seq'::regclass);


--
-- TOC entry 4254 (class 2604 OID 16495)
-- Name: stock_analyst_consensus id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus ALTER COLUMN id SET DEFAULT nextval('public.stock_analyst_consensus_id_seq'::regclass);


--
-- TOC entry 4290 (class 2604 OID 16955)
-- Name: stock_corporate_actions id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions ALTER COLUMN id SET DEFAULT nextval('public.stock_corporate_actions_id_seq'::regclass);


--
-- TOC entry 4288 (class 2604 OID 16937)
-- Name: stock_disclosures id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures ALTER COLUMN id SET DEFAULT nextval('public.stock_disclosures_id_seq'::regclass);


--
-- TOC entry 4260 (class 2604 OID 16529)
-- Name: stock_etf_holders id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders ALTER COLUMN id SET DEFAULT nextval('public.stock_etf_holders_id_seq'::regclass);


--
-- TOC entry 4251 (class 2604 OID 16479)
-- Name: stock_financials id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials ALTER COLUMN id SET DEFAULT nextval('public.stock_financials_id_seq'::regclass);


--
-- TOC entry 4256 (class 2604 OID 16510)
-- Name: stock_management id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management ALTER COLUMN id SET DEFAULT nextval('public.stock_management_id_seq'::regclass);


--
-- TOC entry 4245 (class 2604 OID 16433)
-- Name: stock_market_daily id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily ALTER COLUMN id SET DEFAULT nextval('public.stock_market_daily_id_seq'::regclass);


--
-- TOC entry 4264 (class 2604 OID 16635)
-- Name: stock_news id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news ALTER COLUMN id SET DEFAULT nextval('public.stock_news_id_seq'::regclass);


--
-- TOC entry 4247 (class 2604 OID 16449)
-- Name: stock_performance_daily id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily ALTER COLUMN id SET DEFAULT nextval('public.stock_performance_daily_id_seq'::regclass);


--
-- TOC entry 4281 (class 2604 OID 16883)
-- Name: stock_recommendations id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations ALTER COLUMN id SET DEFAULT nextval('public.stock_recommendations_id_seq'::regclass);


--
-- TOC entry 4286 (class 2604 OID 16922)
-- Name: stock_technicals id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals ALTER COLUMN id SET DEFAULT nextval('public.stock_technicals_id_seq'::regclass);


--
-- TOC entry 4249 (class 2604 OID 16464)
-- Name: stock_valuation id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation ALTER COLUMN id SET DEFAULT nextval('public.stock_valuation_id_seq'::regclass);


--
-- TOC entry 4241 (class 2604 OID 16414)
-- Name: stocks id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks ALTER COLUMN id SET DEFAULT nextval('public.stocks_id_seq'::regclass);


--
-- TOC entry 4266 (class 2604 OID 16790)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 4272 (class 2604 OID 16819)
-- Name: watchlist_items id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items ALTER COLUMN id SET DEFAULT nextval('public.watchlist_items_id_seq'::regclass);


--
-- TOC entry 4269 (class 2604 OID 16803)
-- Name: watchlists id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists ALTER COLUMN id SET DEFAULT nextval('public.watchlists_id_seq'::regclass);


--
-- TOC entry 4299 (class 2606 OID 16409)
-- Name: exchanges exchanges_code_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_code_key UNIQUE (code);


--
-- TOC entry 4301 (class 2606 OID 16407)
-- Name: exchanges exchanges_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_pkey PRIMARY KEY (id);


--
-- TOC entry 4356 (class 2606 OID 16850)
-- Name: portfolio_positions portfolio_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_pkey PRIMARY KEY (id);


--
-- TOC entry 4358 (class 2606 OID 16873)
-- Name: portfolio_trades portfolio_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades
    ADD CONSTRAINT portfolio_trades_pkey PRIMARY KEY (id);


--
-- TOC entry 4366 (class 2606 OID 16910)
-- Name: position_recommendations position_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_pkey PRIMARY KEY (id);


--
-- TOC entry 4368 (class 2606 OID 16912)
-- Name: position_recommendations position_recommendations_position_id_score_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_position_id_score_date_key UNIQUE (position_id, score_date);


--
-- TOC entry 4336 (class 2606 OID 16551)
-- Name: scrape_runs scrape_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 4324 (class 2606 OID 16498)
-- Name: stock_analyst_consensus stock_analyst_consensus_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_pkey PRIMARY KEY (id);


--
-- TOC entry 4326 (class 2606 OID 16500)
-- Name: stock_analyst_consensus stock_analyst_consensus_stock_id_consensus_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_stock_id_consensus_date_key UNIQUE (stock_id, consensus_date);


--
-- TOC entry 4379 (class 2606 OID 16960)
-- Name: stock_corporate_actions stock_corporate_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_pkey PRIMARY KEY (id);


--
-- TOC entry 4381 (class 2606 OID 16962)
-- Name: stock_corporate_actions stock_corporate_actions_stock_id_action_date_action_type_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_stock_id_action_date_action_type_key UNIQUE (stock_id, action_date, action_type);


--
-- TOC entry 4375 (class 2606 OID 16942)
-- Name: stock_disclosures stock_disclosures_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_pkey PRIMARY KEY (id);


--
-- TOC entry 4377 (class 2606 OID 16944)
-- Name: stock_disclosures stock_disclosures_stock_id_disclosure_date_title_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_stock_id_disclosure_date_title_key UNIQUE (stock_id, disclosure_date, title);


--
-- TOC entry 4332 (class 2606 OID 16534)
-- Name: stock_etf_holders stock_etf_holders_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_pkey PRIMARY KEY (id);


--
-- TOC entry 4334 (class 2606 OID 16536)
-- Name: stock_etf_holders stock_etf_holders_stock_id_etf_name_source_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_stock_id_etf_name_source_date_key UNIQUE (stock_id, etf_name, source_date);


--
-- TOC entry 4320 (class 2606 OID 16483)
-- Name: stock_financials stock_financials_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_pkey PRIMARY KEY (id);


--
-- TOC entry 4322 (class 2606 OID 16485)
-- Name: stock_financials stock_financials_stock_id_fiscal_year_period_type_statement_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_stock_id_fiscal_year_period_type_statement_key UNIQUE (stock_id, fiscal_year, period_type, statement_type, is_estimate);


--
-- TOC entry 4383 (class 2606 OID 16973)
-- Name: stock_latest_snapshot stock_latest_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_latest_snapshot
    ADD CONSTRAINT stock_latest_snapshot_pkey PRIMARY KEY (stock_id);


--
-- TOC entry 4328 (class 2606 OID 16517)
-- Name: stock_management stock_management_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_pkey PRIMARY KEY (id);


--
-- TOC entry 4330 (class 2606 OID 16519)
-- Name: stock_management stock_management_stock_id_person_name_title_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_stock_id_person_name_title_key UNIQUE (stock_id, person_name, title);


--
-- TOC entry 4308 (class 2606 OID 16436)
-- Name: stock_market_daily stock_market_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_pkey PRIMARY KEY (id);


--
-- TOC entry 4310 (class 2606 OID 16438)
-- Name: stock_market_daily stock_market_daily_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4339 (class 2606 OID 16640)
-- Name: stock_news stock_news_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_pkey PRIMARY KEY (id);


--
-- TOC entry 4341 (class 2606 OID 16642)
-- Name: stock_news stock_news_stock_id_headline_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_stock_id_headline_key UNIQUE (stock_id, headline);


--
-- TOC entry 4312 (class 2606 OID 16452)
-- Name: stock_performance_daily stock_performance_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_pkey PRIMARY KEY (id);


--
-- TOC entry 4314 (class 2606 OID 16454)
-- Name: stock_performance_daily stock_performance_daily_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4362 (class 2606 OID 16890)
-- Name: stock_recommendations stock_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_pkey PRIMARY KEY (id);


--
-- TOC entry 4364 (class 2606 OID 16892)
-- Name: stock_recommendations stock_recommendations_stock_id_score_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_stock_id_score_date_key UNIQUE (stock_id, score_date);


--
-- TOC entry 4370 (class 2606 OID 16925)
-- Name: stock_technicals stock_technicals_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_pkey PRIMARY KEY (id);


--
-- TOC entry 4372 (class 2606 OID 16927)
-- Name: stock_technicals stock_technicals_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4316 (class 2606 OID 16467)
-- Name: stock_valuation stock_valuation_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_pkey PRIMARY KEY (id);


--
-- TOC entry 4318 (class 2606 OID 16469)
-- Name: stock_valuation stock_valuation_stock_id_fiscal_year_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_stock_id_fiscal_year_key UNIQUE (stock_id, fiscal_year);


--
-- TOC entry 4303 (class 2606 OID 16423)
-- Name: stocks stocks_exchange_id_ticker_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_exchange_id_ticker_key UNIQUE (exchange_id, ticker);


--
-- TOC entry 4305 (class 2606 OID 16421)
-- Name: stocks stocks_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_pkey PRIMARY KEY (id);


--
-- TOC entry 4343 (class 2606 OID 16798)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4345 (class 2606 OID 16796)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4351 (class 2606 OID 16824)
-- Name: watchlist_items watchlist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_pkey PRIMARY KEY (id);


--
-- TOC entry 4353 (class 2606 OID 16826)
-- Name: watchlist_items watchlist_items_watchlist_id_stock_id_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_stock_id_key UNIQUE (watchlist_id, stock_id);


--
-- TOC entry 4347 (class 2606 OID 16807)
-- Name: watchlists watchlists_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_pkey PRIMARY KEY (id);


--
-- TOC entry 4349 (class 2606 OID 16809)
-- Name: watchlists watchlists_user_id_name_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_user_id_name_key UNIQUE (user_id, name);


--
-- TOC entry 4373 (class 1259 OID 16950)
-- Name: idx_disclosures_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_disclosures_stock_date ON public.stock_disclosures USING btree (stock_id, disclosure_date DESC);


--
-- TOC entry 4354 (class 1259 OID 16861)
-- Name: idx_portfolio_user; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_portfolio_user ON public.portfolio_positions USING btree (user_id, is_open);


--
-- TOC entry 4359 (class 1259 OID 16898)
-- Name: idx_recommendations_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_recommendations_stock_date ON public.stock_recommendations USING btree (stock_id, score_date DESC);


--
-- TOC entry 4360 (class 1259 OID 16899)
-- Name: idx_recommendations_verdict; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_recommendations_verdict ON public.stock_recommendations USING btree (score_date DESC, verdict);


--
-- TOC entry 4306 (class 1259 OID 16444)
-- Name: idx_stock_market_daily_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_stock_market_daily_stock_date ON public.stock_market_daily USING btree (stock_id, trading_date DESC);


--
-- TOC entry 4337 (class 1259 OID 16648)
-- Name: idx_stock_news_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_stock_news_stock_date ON public.stock_news USING btree (stock_id, news_date DESC);


--
-- TOC entry 4397 (class 2606 OID 16856)
-- Name: portfolio_positions portfolio_positions_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4398 (class 2606 OID 16851)
-- Name: portfolio_positions portfolio_positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4399 (class 2606 OID 16874)
-- Name: portfolio_trades portfolio_trades_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades
    ADD CONSTRAINT portfolio_trades_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.portfolio_positions(id) ON DELETE CASCADE;


--
-- TOC entry 4401 (class 2606 OID 16913)
-- Name: position_recommendations position_recommendations_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.portfolio_positions(id) ON DELETE CASCADE;


--
-- TOC entry 4392 (class 2606 OID 16552)
-- Name: scrape_runs scrape_runs_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4389 (class 2606 OID 16501)
-- Name: stock_analyst_consensus stock_analyst_consensus_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4404 (class 2606 OID 16963)
-- Name: stock_corporate_actions stock_corporate_actions_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4403 (class 2606 OID 16945)
-- Name: stock_disclosures stock_disclosures_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4391 (class 2606 OID 16537)
-- Name: stock_etf_holders stock_etf_holders_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4388 (class 2606 OID 16486)
-- Name: stock_financials stock_financials_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4405 (class 2606 OID 16974)
-- Name: stock_latest_snapshot stock_latest_snapshot_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_latest_snapshot
    ADD CONSTRAINT stock_latest_snapshot_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4390 (class 2606 OID 16520)
-- Name: stock_management stock_management_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4385 (class 2606 OID 16439)
-- Name: stock_market_daily stock_market_daily_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4393 (class 2606 OID 16643)
-- Name: stock_news stock_news_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4386 (class 2606 OID 16455)
-- Name: stock_performance_daily stock_performance_daily_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4400 (class 2606 OID 16893)
-- Name: stock_recommendations stock_recommendations_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4402 (class 2606 OID 16928)
-- Name: stock_technicals stock_technicals_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4387 (class 2606 OID 16470)
-- Name: stock_valuation stock_valuation_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4384 (class 2606 OID 16424)
-- Name: stocks stocks_exchange_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_exchange_id_fkey FOREIGN KEY (exchange_id) REFERENCES public.exchanges(id);


--
-- TOC entry 4395 (class 2606 OID 16832)
-- Name: watchlist_items watchlist_items_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4396 (class 2606 OID 16827)
-- Name: watchlist_items watchlist_items_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(id) ON DELETE CASCADE;


--
-- TOC entry 4394 (class 2606 OID 16810)
-- Name: watchlists watchlists_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


-- Completed on 2026-05-07 19:01:38

--
-- PostgreSQL database dump complete
--

\unrestrict 7jpAa23pHdYRH6H4l6DnTM8rQiQ2nyvGqgrz6SPo37BkrxfDSSquIIjfu2OFR1B

