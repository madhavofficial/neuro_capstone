-- Migration 002: Schema Refinements & RLS Policies
-- Use this migration if you have already executed 001_initial_schema.sql previously in your Supabase dashboard.

-- 1. Support both 1-letter (A, T) and 3-letter (Ala, Thr) amino acid codes
alter table public.variants 
    alter column wild_type_aa type varchar(8),
    alter column mutant_aa type varchar(8);

-- 2. Fast cache lookup index on pipeline runs
create index if not exists idx_pipeline_runs_variant_lookup 
    on public.pipeline_runs(variant_id, confidence_threshold);

-- 3. Row Level Security (RLS) public read policies (allows frontend clients to select data)
create policy if not exists "Allow public read access" on public.proteins for select using (true);
create policy if not exists "Allow public read access" on public.variants for select using (true);
create policy if not exists "Allow public read access" on public.clinical_cache for select using (true);
create policy if not exists "Allow public read access" on public.biophysics_metrics for select using (true);
create policy if not exists "Allow public read access" on public.pipeline_runs for select using (true);
