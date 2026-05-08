--
-- PostgreSQL database dump
--

\restrict BaoLgoPjzojkChl1F2vYaEeKiC7Gh9JX9QIXm3oQ5yIgN1Fe0ezGkZq5dQNrVjA

-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.2

-- Started on 2026-05-08 08:43:42

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

--
-- TOC entry 275 (class 1255 OID 17161)
-- Name: set_updated_at_now(); Type: FUNCTION; Schema: public; Owner: magedzamzam
--

CREATE FUNCTION public.set_updated_at_now() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at_now() OWNER TO magedzamzam;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 270 (class 1259 OID 17074)
-- Name: broker_instruments; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.broker_instruments (
    id bigint NOT NULL,
    broker_id bigint NOT NULL,
    broker_symbol character varying(64) NOT NULL,
    broker_name character varying(255),
    instrument_type character varying(32),
    stock_id bigint,
    currency character varying(8),
    min_qty numeric(20,6),
    is_tradeable boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.broker_instruments OWNER TO magedzamzam;

--
-- TOC entry 269 (class 1259 OID 17073)
-- Name: broker_instruments_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.broker_instruments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.broker_instruments_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4647 (class 0 OID 0)
-- Dependencies: 269
-- Name: broker_instruments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.broker_instruments_id_seq OWNED BY public.broker_instruments.id;


--
-- TOC entry 272 (class 1259 OID 17097)
-- Name: broker_orders; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.broker_orders (
    id bigint NOT NULL,
    account_id bigint NOT NULL,
    user_id bigint NOT NULL,
    stock_id bigint,
    broker_symbol character varying(64),
    side character varying(8) NOT NULL,
    order_type character varying(8) NOT NULL,
    quantity numeric(20,6) NOT NULL,
    limit_price numeric(20,6),
    stop_loss numeric(20,6),
    take_profit numeric(20,6),
    currency character varying(8),
    broker_order_ref character varying(120),
    status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    fill_price numeric(20,6),
    fill_quantity numeric(20,6),
    rejection_reason text,
    notes text,
    placed_at timestamp without time zone DEFAULT now() NOT NULL,
    filled_at timestamp without time zone,
    last_synced_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT broker_orders_order_type_check CHECK (((order_type)::text = ANY ((ARRAY['MARKET'::character varying, 'LIMIT'::character varying, 'STOP'::character varying])::text[]))),
    CONSTRAINT broker_orders_quantity_check CHECK ((quantity > (0)::numeric)),
    CONSTRAINT broker_orders_side_check CHECK (((side)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying])::text[]))),
    CONSTRAINT broker_orders_status_check CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'WORKING'::character varying, 'FILLED'::character varying, 'CANCELLED'::character varying, 'REJECTED'::character varying])::text[])))
);


ALTER TABLE public.broker_orders OWNER TO magedzamzam;

--
-- TOC entry 271 (class 1259 OID 17096)
-- Name: broker_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.broker_orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.broker_orders_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4648 (class 0 OID 0)
-- Dependencies: 271
-- Name: broker_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.broker_orders_id_seq OWNED BY public.broker_orders.id;


--
-- TOC entry 274 (class 1259 OID 17132)
-- Name: broker_positions_snapshot; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.broker_positions_snapshot (
    id bigint NOT NULL,
    account_id bigint NOT NULL,
    stock_id bigint,
    broker_symbol character varying(64) NOT NULL,
    quantity numeric(20,6) NOT NULL,
    avg_open_price numeric(20,6),
    current_price numeric(20,6),
    unrealized_pl numeric(20,6),
    unrealized_pl_pct numeric(8,4),
    currency character varying(8),
    direction character varying(8),
    raw jsonb,
    fetched_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT broker_positions_snapshot_direction_check CHECK (((direction)::text = ANY ((ARRAY['LONG'::character varying, 'SHORT'::character varying])::text[])))
);


ALTER TABLE public.broker_positions_snapshot OWNER TO magedzamzam;

--
-- TOC entry 273 (class 1259 OID 17131)
-- Name: broker_positions_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.broker_positions_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.broker_positions_snapshot_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4649 (class 0 OID 0)
-- Dependencies: 273
-- Name: broker_positions_snapshot_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.broker_positions_snapshot_id_seq OWNED BY public.broker_positions_snapshot.id;


--
-- TOC entry 266 (class 1259 OID 17033)
-- Name: brokers; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.brokers (
    id bigint NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(120) NOT NULL,
    kind character varying(16) NOT NULL,
    adapter_class character varying(120) NOT NULL,
    base_url character varying(255),
    docs_url character varying(255),
    credential_schema jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT brokers_kind_check CHECK (((kind)::text = ANY ((ARRAY['automated'::character varying, 'manual'::character varying])::text[])))
);


ALTER TABLE public.brokers OWNER TO magedzamzam;

--
-- TOC entry 265 (class 1259 OID 17032)
-- Name: brokers_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.brokers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.brokers_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4650 (class 0 OID 0)
-- Dependencies: 265
-- Name: brokers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.brokers_id_seq OWNED BY public.brokers.id;


--
-- TOC entry 222 (class 1259 OID 16402)
-- Name: exchanges; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.exchanges (
    id integer NOT NULL,
    code character varying(10) NOT NULL,
    name character varying(100) NOT NULL,
    country character varying(100),
    currency character varying(4)
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
-- TOC entry 4651 (class 0 OID 0)
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
    account_id bigint,
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
-- TOC entry 4652 (class 0 OID 0)
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
-- TOC entry 4653 (class 0 OID 0)
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
-- TOC entry 4654 (class 0 OID 0)
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
-- TOC entry 4655 (class 0 OID 0)
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
-- TOC entry 4656 (class 0 OID 0)
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
-- TOC entry 4657 (class 0 OID 0)
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
-- TOC entry 4658 (class 0 OID 0)
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
-- TOC entry 4659 (class 0 OID 0)
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
-- TOC entry 4660 (class 0 OID 0)
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
-- TOC entry 4661 (class 0 OID 0)
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
-- TOC entry 4662 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.revenue_ttm; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.revenue_ttm IS 'Revenue metric from ListOfCompanies CSV snapshot; fiscal-year context is not supplied.';


--
-- TOC entry 4663 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.dividend_growth_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.dividend_growth_pct IS 'Dividend growth percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4664 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.ex_dividend_date; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.ex_dividend_date IS 'Ex-dividend date from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4665 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.payout_ratio_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.payout_ratio_pct IS 'Payout ratio percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4666 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.payout_frequency; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.payout_frequency IS 'Payout frequency from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4667 (class 0 OID 0)
-- Dependencies: 226
-- Name: COLUMN stock_market_daily.week_52_low_change_pct; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_market_daily.week_52_low_change_pct IS 'Current price change from 52-week low, as displayed in ListOfCompanies CSV snapshot.';


--
-- TOC entry 4668 (class 0 OID 0)
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
-- TOC entry 4669 (class 0 OID 0)
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
-- TOC entry 4670 (class 0 OID 0)
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
-- TOC entry 4671 (class 0 OID 0)
-- Dependencies: 228
-- Name: COLUMN stock_performance_daily.return_5y; Type: COMMENT; Schema: public; Owner: magedzamzam
--

COMMENT ON COLUMN public.stock_performance_daily.return_5y IS 'Five-year return percentage from ListOfCompanies CSV snapshot.';


--
-- TOC entry 4672 (class 0 OID 0)
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
-- TOC entry 4673 (class 0 OID 0)
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
-- TOC entry 4674 (class 0 OID 0)
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
-- TOC entry 4675 (class 0 OID 0)
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
-- TOC entry 4676 (class 0 OID 0)
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
-- TOC entry 4677 (class 0 OID 0)
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
-- TOC entry 4678 (class 0 OID 0)
-- Dependencies: 223
-- Name: stocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.stocks_id_seq OWNED BY public.stocks.id;


--
-- TOC entry 268 (class 1259 OID 17048)
-- Name: trading_accounts; Type: TABLE; Schema: public; Owner: magedzamzam
--

CREATE TABLE public.trading_accounts (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    broker_id bigint NOT NULL,
    label character varying(120) NOT NULL,
    currency character varying(8),
    credentials_encrypted bytea,
    credentials_nonce bytea,
    display_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_connect_status character varying(16),
    last_connect_error text,
    last_connect_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.trading_accounts OWNER TO magedzamzam;

--
-- TOC entry 267 (class 1259 OID 17047)
-- Name: trading_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: magedzamzam
--

CREATE SEQUENCE public.trading_accounts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.trading_accounts_id_seq OWNER TO magedzamzam;

--
-- TOC entry 4679 (class 0 OID 0)
-- Dependencies: 267
-- Name: trading_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.trading_accounts_id_seq OWNED BY public.trading_accounts.id;


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
-- TOC entry 4680 (class 0 OID 0)
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
-- TOC entry 4681 (class 0 OID 0)
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
-- TOC entry 4682 (class 0 OID 0)
-- Dependencies: 245
-- Name: watchlists_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: magedzamzam
--

ALTER SEQUENCE public.watchlists_id_seq OWNED BY public.watchlists.id;


--
-- TOC entry 4328 (class 2604 OID 17077)
-- Name: broker_instruments id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_instruments ALTER COLUMN id SET DEFAULT nextval('public.broker_instruments_id_seq'::regclass);


--
-- TOC entry 4332 (class 2604 OID 17100)
-- Name: broker_orders id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_orders ALTER COLUMN id SET DEFAULT nextval('public.broker_orders_id_seq'::regclass);


--
-- TOC entry 4337 (class 2604 OID 17135)
-- Name: broker_positions_snapshot id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_positions_snapshot ALTER COLUMN id SET DEFAULT nextval('public.broker_positions_snapshot_id_seq'::regclass);


--
-- TOC entry 4319 (class 2604 OID 17036)
-- Name: brokers id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.brokers ALTER COLUMN id SET DEFAULT nextval('public.brokers_id_seq'::regclass);


--
-- TOC entry 4266 (class 2604 OID 16405)
-- Name: exchanges id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges ALTER COLUMN id SET DEFAULT nextval('public.exchanges_id_seq'::regclass);


--
-- TOC entry 4300 (class 2604 OID 16841)
-- Name: portfolio_positions id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions ALTER COLUMN id SET DEFAULT nextval('public.portfolio_positions_id_seq'::regclass);


--
-- TOC entry 4304 (class 2604 OID 16866)
-- Name: portfolio_trades id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades ALTER COLUMN id SET DEFAULT nextval('public.portfolio_trades_id_seq'::regclass);


--
-- TOC entry 4310 (class 2604 OID 16904)
-- Name: position_recommendations id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations ALTER COLUMN id SET DEFAULT nextval('public.position_recommendations_id_seq'::regclass);


--
-- TOC entry 4288 (class 2604 OID 16546)
-- Name: scrape_runs id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs ALTER COLUMN id SET DEFAULT nextval('public.scrape_runs_id_seq'::regclass);


--
-- TOC entry 4280 (class 2604 OID 16495)
-- Name: stock_analyst_consensus id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus ALTER COLUMN id SET DEFAULT nextval('public.stock_analyst_consensus_id_seq'::regclass);


--
-- TOC entry 4316 (class 2604 OID 16955)
-- Name: stock_corporate_actions id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions ALTER COLUMN id SET DEFAULT nextval('public.stock_corporate_actions_id_seq'::regclass);


--
-- TOC entry 4314 (class 2604 OID 16937)
-- Name: stock_disclosures id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures ALTER COLUMN id SET DEFAULT nextval('public.stock_disclosures_id_seq'::regclass);


--
-- TOC entry 4286 (class 2604 OID 16529)
-- Name: stock_etf_holders id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders ALTER COLUMN id SET DEFAULT nextval('public.stock_etf_holders_id_seq'::regclass);


--
-- TOC entry 4277 (class 2604 OID 16479)
-- Name: stock_financials id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials ALTER COLUMN id SET DEFAULT nextval('public.stock_financials_id_seq'::regclass);


--
-- TOC entry 4282 (class 2604 OID 16510)
-- Name: stock_management id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management ALTER COLUMN id SET DEFAULT nextval('public.stock_management_id_seq'::regclass);


--
-- TOC entry 4271 (class 2604 OID 16433)
-- Name: stock_market_daily id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily ALTER COLUMN id SET DEFAULT nextval('public.stock_market_daily_id_seq'::regclass);


--
-- TOC entry 4290 (class 2604 OID 16635)
-- Name: stock_news id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news ALTER COLUMN id SET DEFAULT nextval('public.stock_news_id_seq'::regclass);


--
-- TOC entry 4273 (class 2604 OID 16449)
-- Name: stock_performance_daily id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily ALTER COLUMN id SET DEFAULT nextval('public.stock_performance_daily_id_seq'::regclass);


--
-- TOC entry 4307 (class 2604 OID 16883)
-- Name: stock_recommendations id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations ALTER COLUMN id SET DEFAULT nextval('public.stock_recommendations_id_seq'::regclass);


--
-- TOC entry 4312 (class 2604 OID 16922)
-- Name: stock_technicals id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals ALTER COLUMN id SET DEFAULT nextval('public.stock_technicals_id_seq'::regclass);


--
-- TOC entry 4275 (class 2604 OID 16464)
-- Name: stock_valuation id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation ALTER COLUMN id SET DEFAULT nextval('public.stock_valuation_id_seq'::regclass);


--
-- TOC entry 4267 (class 2604 OID 16414)
-- Name: stocks id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks ALTER COLUMN id SET DEFAULT nextval('public.stocks_id_seq'::regclass);


--
-- TOC entry 4323 (class 2604 OID 17051)
-- Name: trading_accounts id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.trading_accounts ALTER COLUMN id SET DEFAULT nextval('public.trading_accounts_id_seq'::regclass);


--
-- TOC entry 4292 (class 2604 OID 16790)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 4298 (class 2604 OID 16819)
-- Name: watchlist_items id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items ALTER COLUMN id SET DEFAULT nextval('public.watchlist_items_id_seq'::regclass);


--
-- TOC entry 4295 (class 2604 OID 16803)
-- Name: watchlists id; Type: DEFAULT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists ALTER COLUMN id SET DEFAULT nextval('public.watchlists_id_seq'::regclass);


--
-- TOC entry 4447 (class 2606 OID 17084)
-- Name: broker_instruments broker_instruments_broker_id_broker_symbol_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_instruments
    ADD CONSTRAINT broker_instruments_broker_id_broker_symbol_key UNIQUE (broker_id, broker_symbol);


--
-- TOC entry 4449 (class 2606 OID 17082)
-- Name: broker_instruments broker_instruments_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_instruments
    ADD CONSTRAINT broker_instruments_pkey PRIMARY KEY (id);


--
-- TOC entry 4452 (class 2606 OID 17112)
-- Name: broker_orders broker_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_orders
    ADD CONSTRAINT broker_orders_pkey PRIMARY KEY (id);


--
-- TOC entry 4457 (class 2606 OID 17143)
-- Name: broker_positions_snapshot broker_positions_snapshot_account_id_broker_symbol_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_positions_snapshot
    ADD CONSTRAINT broker_positions_snapshot_account_id_broker_symbol_key UNIQUE (account_id, broker_symbol);


--
-- TOC entry 4459 (class 2606 OID 17141)
-- Name: broker_positions_snapshot broker_positions_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_positions_snapshot
    ADD CONSTRAINT broker_positions_snapshot_pkey PRIMARY KEY (id);


--
-- TOC entry 4438 (class 2606 OID 17046)
-- Name: brokers brokers_code_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.brokers
    ADD CONSTRAINT brokers_code_key UNIQUE (code);


--
-- TOC entry 4440 (class 2606 OID 17044)
-- Name: brokers brokers_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.brokers
    ADD CONSTRAINT brokers_pkey PRIMARY KEY (id);


--
-- TOC entry 4351 (class 2606 OID 16409)
-- Name: exchanges exchanges_code_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_code_key UNIQUE (code);


--
-- TOC entry 4353 (class 2606 OID 16407)
-- Name: exchanges exchanges_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.exchanges
    ADD CONSTRAINT exchanges_pkey PRIMARY KEY (id);


--
-- TOC entry 4409 (class 2606 OID 16850)
-- Name: portfolio_positions portfolio_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_pkey PRIMARY KEY (id);


--
-- TOC entry 4411 (class 2606 OID 16873)
-- Name: portfolio_trades portfolio_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades
    ADD CONSTRAINT portfolio_trades_pkey PRIMARY KEY (id);


--
-- TOC entry 4419 (class 2606 OID 16910)
-- Name: position_recommendations position_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_pkey PRIMARY KEY (id);


--
-- TOC entry 4421 (class 2606 OID 16912)
-- Name: position_recommendations position_recommendations_position_id_score_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_position_id_score_date_key UNIQUE (position_id, score_date);


--
-- TOC entry 4388 (class 2606 OID 16551)
-- Name: scrape_runs scrape_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 4376 (class 2606 OID 16498)
-- Name: stock_analyst_consensus stock_analyst_consensus_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_pkey PRIMARY KEY (id);


--
-- TOC entry 4378 (class 2606 OID 16500)
-- Name: stock_analyst_consensus stock_analyst_consensus_stock_id_consensus_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_stock_id_consensus_date_key UNIQUE (stock_id, consensus_date);


--
-- TOC entry 4432 (class 2606 OID 16960)
-- Name: stock_corporate_actions stock_corporate_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_pkey PRIMARY KEY (id);


--
-- TOC entry 4434 (class 2606 OID 16962)
-- Name: stock_corporate_actions stock_corporate_actions_stock_id_action_date_action_type_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_stock_id_action_date_action_type_key UNIQUE (stock_id, action_date, action_type);


--
-- TOC entry 4428 (class 2606 OID 16942)
-- Name: stock_disclosures stock_disclosures_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_pkey PRIMARY KEY (id);


--
-- TOC entry 4430 (class 2606 OID 16944)
-- Name: stock_disclosures stock_disclosures_stock_id_disclosure_date_title_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_stock_id_disclosure_date_title_key UNIQUE (stock_id, disclosure_date, title);


--
-- TOC entry 4384 (class 2606 OID 16534)
-- Name: stock_etf_holders stock_etf_holders_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_pkey PRIMARY KEY (id);


--
-- TOC entry 4386 (class 2606 OID 16536)
-- Name: stock_etf_holders stock_etf_holders_stock_id_etf_name_source_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_stock_id_etf_name_source_date_key UNIQUE (stock_id, etf_name, source_date);


--
-- TOC entry 4372 (class 2606 OID 16483)
-- Name: stock_financials stock_financials_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_pkey PRIMARY KEY (id);


--
-- TOC entry 4374 (class 2606 OID 16485)
-- Name: stock_financials stock_financials_stock_id_fiscal_year_period_type_statement_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_stock_id_fiscal_year_period_type_statement_key UNIQUE (stock_id, fiscal_year, period_type, statement_type, is_estimate);


--
-- TOC entry 4436 (class 2606 OID 16973)
-- Name: stock_latest_snapshot stock_latest_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_latest_snapshot
    ADD CONSTRAINT stock_latest_snapshot_pkey PRIMARY KEY (stock_id);


--
-- TOC entry 4380 (class 2606 OID 16517)
-- Name: stock_management stock_management_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_pkey PRIMARY KEY (id);


--
-- TOC entry 4382 (class 2606 OID 16519)
-- Name: stock_management stock_management_stock_id_person_name_title_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_stock_id_person_name_title_key UNIQUE (stock_id, person_name, title);


--
-- TOC entry 4360 (class 2606 OID 16436)
-- Name: stock_market_daily stock_market_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_pkey PRIMARY KEY (id);


--
-- TOC entry 4362 (class 2606 OID 16438)
-- Name: stock_market_daily stock_market_daily_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4391 (class 2606 OID 16640)
-- Name: stock_news stock_news_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_pkey PRIMARY KEY (id);


--
-- TOC entry 4393 (class 2606 OID 16642)
-- Name: stock_news stock_news_stock_id_headline_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_stock_id_headline_key UNIQUE (stock_id, headline);


--
-- TOC entry 4364 (class 2606 OID 16452)
-- Name: stock_performance_daily stock_performance_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_pkey PRIMARY KEY (id);


--
-- TOC entry 4366 (class 2606 OID 16454)
-- Name: stock_performance_daily stock_performance_daily_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4415 (class 2606 OID 16890)
-- Name: stock_recommendations stock_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_pkey PRIMARY KEY (id);


--
-- TOC entry 4417 (class 2606 OID 16892)
-- Name: stock_recommendations stock_recommendations_stock_id_score_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_stock_id_score_date_key UNIQUE (stock_id, score_date);


--
-- TOC entry 4423 (class 2606 OID 16925)
-- Name: stock_technicals stock_technicals_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_pkey PRIMARY KEY (id);


--
-- TOC entry 4425 (class 2606 OID 16927)
-- Name: stock_technicals stock_technicals_stock_id_trading_date_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_stock_id_trading_date_key UNIQUE (stock_id, trading_date);


--
-- TOC entry 4368 (class 2606 OID 16467)
-- Name: stock_valuation stock_valuation_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_pkey PRIMARY KEY (id);


--
-- TOC entry 4370 (class 2606 OID 16469)
-- Name: stock_valuation stock_valuation_stock_id_fiscal_year_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_stock_id_fiscal_year_key UNIQUE (stock_id, fiscal_year);


--
-- TOC entry 4355 (class 2606 OID 16423)
-- Name: stocks stocks_exchange_id_ticker_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_exchange_id_ticker_key UNIQUE (exchange_id, ticker);


--
-- TOC entry 4357 (class 2606 OID 16421)
-- Name: stocks stocks_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_pkey PRIMARY KEY (id);


--
-- TOC entry 4443 (class 2606 OID 17059)
-- Name: trading_accounts trading_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_pkey PRIMARY KEY (id);


--
-- TOC entry 4445 (class 2606 OID 17061)
-- Name: trading_accounts trading_accounts_user_id_broker_id_label_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_user_id_broker_id_label_key UNIQUE (user_id, broker_id, label);


--
-- TOC entry 4395 (class 2606 OID 16798)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4397 (class 2606 OID 16796)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4403 (class 2606 OID 16824)
-- Name: watchlist_items watchlist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_pkey PRIMARY KEY (id);


--
-- TOC entry 4405 (class 2606 OID 16826)
-- Name: watchlist_items watchlist_items_watchlist_id_stock_id_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_stock_id_key UNIQUE (watchlist_id, stock_id);


--
-- TOC entry 4399 (class 2606 OID 16807)
-- Name: watchlists watchlists_pkey; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_pkey PRIMARY KEY (id);


--
-- TOC entry 4401 (class 2606 OID 16809)
-- Name: watchlists watchlists_user_id_name_key; Type: CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_user_id_name_key UNIQUE (user_id, name);


--
-- TOC entry 4426 (class 1259 OID 16950)
-- Name: idx_disclosures_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_disclosures_stock_date ON public.stock_disclosures USING btree (stock_id, disclosure_date DESC);


--
-- TOC entry 4406 (class 1259 OID 16861)
-- Name: idx_portfolio_user; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_portfolio_user ON public.portfolio_positions USING btree (user_id, is_open);


--
-- TOC entry 4412 (class 1259 OID 16898)
-- Name: idx_recommendations_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_recommendations_stock_date ON public.stock_recommendations USING btree (stock_id, score_date DESC);


--
-- TOC entry 4413 (class 1259 OID 16899)
-- Name: idx_recommendations_verdict; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_recommendations_verdict ON public.stock_recommendations USING btree (score_date DESC, verdict);


--
-- TOC entry 4358 (class 1259 OID 16444)
-- Name: idx_stock_market_daily_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_stock_market_daily_stock_date ON public.stock_market_daily USING btree (stock_id, trading_date DESC);


--
-- TOC entry 4389 (class 1259 OID 16648)
-- Name: idx_stock_news_stock_date; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX idx_stock_news_stock_date ON public.stock_news USING btree (stock_id, news_date DESC);


--
-- TOC entry 4450 (class 1259 OID 17095)
-- Name: ix_broker_instruments_stock; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_broker_instruments_stock ON public.broker_instruments USING btree (stock_id) WHERE (stock_id IS NOT NULL);


--
-- TOC entry 4453 (class 1259 OID 17128)
-- Name: ix_broker_orders_account; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_broker_orders_account ON public.broker_orders USING btree (account_id, status, placed_at DESC);


--
-- TOC entry 4454 (class 1259 OID 17130)
-- Name: ix_broker_orders_broker_ref; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_broker_orders_broker_ref ON public.broker_orders USING btree (broker_order_ref) WHERE (broker_order_ref IS NOT NULL);


--
-- TOC entry 4455 (class 1259 OID 17129)
-- Name: ix_broker_orders_user_recent; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_broker_orders_user_recent ON public.broker_orders USING btree (user_id, placed_at DESC);


--
-- TOC entry 4460 (class 1259 OID 17154)
-- Name: ix_broker_positions_account; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_broker_positions_account ON public.broker_positions_snapshot USING btree (account_id, fetched_at DESC);


--
-- TOC entry 4407 (class 1259 OID 17160)
-- Name: ix_portfolio_positions_account; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_portfolio_positions_account ON public.portfolio_positions USING btree (account_id);


--
-- TOC entry 4441 (class 1259 OID 17072)
-- Name: ix_trading_accounts_user; Type: INDEX; Schema: public; Owner: magedzamzam
--

CREATE INDEX ix_trading_accounts_user ON public.trading_accounts USING btree (user_id, is_active);


--
-- TOC entry 4494 (class 2620 OID 17166)
-- Name: broker_instruments trg_broker_instruments_updated_at; Type: TRIGGER; Schema: public; Owner: magedzamzam
--

CREATE TRIGGER trg_broker_instruments_updated_at BEFORE UPDATE ON public.broker_instruments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();


--
-- TOC entry 4495 (class 2620 OID 17167)
-- Name: broker_orders trg_broker_orders_updated_at; Type: TRIGGER; Schema: public; Owner: magedzamzam
--

CREATE TRIGGER trg_broker_orders_updated_at BEFORE UPDATE ON public.broker_orders FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();


--
-- TOC entry 4493 (class 2620 OID 17165)
-- Name: trading_accounts trg_trading_accounts_updated_at; Type: TRIGGER; Schema: public; Owner: magedzamzam
--

CREATE TRIGGER trg_trading_accounts_updated_at BEFORE UPDATE ON public.trading_accounts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at_now();


--
-- TOC entry 4486 (class 2606 OID 17085)
-- Name: broker_instruments broker_instruments_broker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_instruments
    ADD CONSTRAINT broker_instruments_broker_id_fkey FOREIGN KEY (broker_id) REFERENCES public.brokers(id) ON DELETE CASCADE;


--
-- TOC entry 4487 (class 2606 OID 17090)
-- Name: broker_instruments broker_instruments_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_instruments
    ADD CONSTRAINT broker_instruments_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE SET NULL;


--
-- TOC entry 4488 (class 2606 OID 17113)
-- Name: broker_orders broker_orders_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_orders
    ADD CONSTRAINT broker_orders_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.trading_accounts(id) ON DELETE CASCADE;


--
-- TOC entry 4489 (class 2606 OID 17123)
-- Name: broker_orders broker_orders_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_orders
    ADD CONSTRAINT broker_orders_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE SET NULL;


--
-- TOC entry 4490 (class 2606 OID 17118)
-- Name: broker_orders broker_orders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_orders
    ADD CONSTRAINT broker_orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4491 (class 2606 OID 17144)
-- Name: broker_positions_snapshot broker_positions_snapshot_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_positions_snapshot
    ADD CONSTRAINT broker_positions_snapshot_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.trading_accounts(id) ON DELETE CASCADE;


--
-- TOC entry 4492 (class 2606 OID 17149)
-- Name: broker_positions_snapshot broker_positions_snapshot_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.broker_positions_snapshot
    ADD CONSTRAINT broker_positions_snapshot_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE SET NULL;


--
-- TOC entry 4474 (class 2606 OID 17155)
-- Name: portfolio_positions portfolio_positions_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.trading_accounts(id) ON DELETE SET NULL;


--
-- TOC entry 4475 (class 2606 OID 16856)
-- Name: portfolio_positions portfolio_positions_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4476 (class 2606 OID 16851)
-- Name: portfolio_positions portfolio_positions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_positions
    ADD CONSTRAINT portfolio_positions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4477 (class 2606 OID 16874)
-- Name: portfolio_trades portfolio_trades_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.portfolio_trades
    ADD CONSTRAINT portfolio_trades_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.portfolio_positions(id) ON DELETE CASCADE;


--
-- TOC entry 4479 (class 2606 OID 16913)
-- Name: position_recommendations position_recommendations_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.position_recommendations
    ADD CONSTRAINT position_recommendations_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.portfolio_positions(id) ON DELETE CASCADE;


--
-- TOC entry 4469 (class 2606 OID 16552)
-- Name: scrape_runs scrape_runs_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4466 (class 2606 OID 16501)
-- Name: stock_analyst_consensus stock_analyst_consensus_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_analyst_consensus
    ADD CONSTRAINT stock_analyst_consensus_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4482 (class 2606 OID 16963)
-- Name: stock_corporate_actions stock_corporate_actions_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_corporate_actions
    ADD CONSTRAINT stock_corporate_actions_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4481 (class 2606 OID 16945)
-- Name: stock_disclosures stock_disclosures_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_disclosures
    ADD CONSTRAINT stock_disclosures_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4468 (class 2606 OID 16537)
-- Name: stock_etf_holders stock_etf_holders_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_etf_holders
    ADD CONSTRAINT stock_etf_holders_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4465 (class 2606 OID 16486)
-- Name: stock_financials stock_financials_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_financials
    ADD CONSTRAINT stock_financials_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4483 (class 2606 OID 16974)
-- Name: stock_latest_snapshot stock_latest_snapshot_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_latest_snapshot
    ADD CONSTRAINT stock_latest_snapshot_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4467 (class 2606 OID 16520)
-- Name: stock_management stock_management_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_management
    ADD CONSTRAINT stock_management_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4462 (class 2606 OID 16439)
-- Name: stock_market_daily stock_market_daily_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_market_daily
    ADD CONSTRAINT stock_market_daily_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4470 (class 2606 OID 16643)
-- Name: stock_news stock_news_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_news
    ADD CONSTRAINT stock_news_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4463 (class 2606 OID 16455)
-- Name: stock_performance_daily stock_performance_daily_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_performance_daily
    ADD CONSTRAINT stock_performance_daily_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4478 (class 2606 OID 16893)
-- Name: stock_recommendations stock_recommendations_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_recommendations
    ADD CONSTRAINT stock_recommendations_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4480 (class 2606 OID 16928)
-- Name: stock_technicals stock_technicals_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_technicals
    ADD CONSTRAINT stock_technicals_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4464 (class 2606 OID 16470)
-- Name: stock_valuation stock_valuation_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stock_valuation
    ADD CONSTRAINT stock_valuation_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id);


--
-- TOC entry 4461 (class 2606 OID 16424)
-- Name: stocks stocks_exchange_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_exchange_id_fkey FOREIGN KEY (exchange_id) REFERENCES public.exchanges(id);


--
-- TOC entry 4484 (class 2606 OID 17067)
-- Name: trading_accounts trading_accounts_broker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_broker_id_fkey FOREIGN KEY (broker_id) REFERENCES public.brokers(id) ON DELETE RESTRICT;


--
-- TOC entry 4485 (class 2606 OID 17062)
-- Name: trading_accounts trading_accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.trading_accounts
    ADD CONSTRAINT trading_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4472 (class 2606 OID 16832)
-- Name: watchlist_items watchlist_items_stock_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_stock_id_fkey FOREIGN KEY (stock_id) REFERENCES public.stocks(id) ON DELETE CASCADE;


--
-- TOC entry 4473 (class 2606 OID 16827)
-- Name: watchlist_items watchlist_items_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlist_items
    ADD CONSTRAINT watchlist_items_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(id) ON DELETE CASCADE;


--
-- TOC entry 4471 (class 2606 OID 16810)
-- Name: watchlists watchlists_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: magedzamzam
--

ALTER TABLE ONLY public.watchlists
    ADD CONSTRAINT watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


-- Completed on 2026-05-08 08:43:43

--
-- PostgreSQL database dump complete
--

\unrestrict BaoLgoPjzojkChl1F2vYaEeKiC7Gh9JX9QIXm3oQ5yIgN1Fe0ezGkZq5dQNrVjA

