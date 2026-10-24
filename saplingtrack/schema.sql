-- SaplingTrack database. Paste this whole file into Supabase: SQL Editor > New query > Run.

create table drives (
  id bigint generated always as identity primary key,
  name text not null,
  location text,
  date date not null default current_date
);

create table volunteers (
  id bigint generated always as identity primary key,
  name text not null,
  phone text,
  token text not null unique
);

create table species (
  name text primary key,
  watering_interval_days int not null check (watering_interval_days > 0)
);

create table saplings (
  id bigint generated always as identity primary key,
  drive_id bigint not null references drives(id),
  sapling_number int not null unique,
  species text not null references species(name),
  latitude double precision not null,
  longitude double precision not null,
  carer_id bigint not null references volunteers(id),   -- specification 2: no sapling without a carer
  status text not null default 'healthy' check (status in ('healthy', 'damaged', 'dead')),
  notes text,
  planted_on date not null default current_date,
  last_watered date
);

create table logs (
  id bigint generated always as identity primary key,
  sapling_id bigint not null references saplings(id),
  type text not null check (type in ('water', 'damage')),
  created_at timestamptz not null default now()
);

-- Lock every table so only the server (using the secret key) can read or write
alter table drives enable row level security;
alter table volunteers enable row level security;
alter table species enable row level security;
alter table saplings enable row level security;
alter table logs enable row level security;

-- Species and watering intervals.
-- REPLACE these numbers with the intervals from your A2 research appendix before running.
insert into species (name, watering_interval_days) values
  ('Neem', 7),
  ('Peepal', 7),
  ('Gulmohar', 5),
  ('Jamun', 5),
  ('Banyan', 7);
