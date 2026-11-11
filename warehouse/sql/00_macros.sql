-- Parsing helpers shared by the core tables (and by tests).

-- Excel day-number (e.g. 42606.5673) to timestamp, rounded to the second.
create or replace macro excel_ts(x) as
    timestamp '1899-12-30' + to_seconds(cast(round(try_cast(x as double) * 86400) as bigint));

-- Trip start/end times: one format per source file, chosen in build.py.
create or replace macro parse_trip_time(x, fmt) as case fmt
    when 'iso'   then try_strptime(x, '%Y-%m-%d %H:%M:%S')
    when 'mdy'   then try_strptime(x, '%m/%d/%Y %H:%M')
    when 'mdy2s' then try_strptime(x, '%m/%d/%y %H:%M:%S')
    when 'dmy'   then try_strptime(x, '%d/%m/%Y %H:%M')
    when 'excel' then excel_ts(x)
    -- 2016 Q4: text is day-first; cells Excel did convert have day and month swapped,
    -- and as the file only covers Oct-Dec the real month sits in the day field (10-12).
    when 'dmy_or_swapped_excel' then case
        when x like '%/%' then try_strptime(x, '%d/%m/%Y %H:%M')
        when day(excel_ts(x)) between 10 and 12 then make_timestamp(
            year(excel_ts(x)), day(excel_ts(x)), month(excel_ts(x)),
            hour(excel_ts(x)), minute(excel_ts(x)), second(excel_ts(x)))
        end
    end;

-- '7130', '7130.0', '' or 'NULL' to integer id or null.
create or replace macro clean_id(x) as try_cast(try_cast(nullif(trim(x), '') as double) as integer);

create or replace macro clean_name(x) as nullif(nullif(regexp_replace(trim(x), '\s+', ' ', 'g'), ''), 'NULL');

create or replace macro user_kind(x) as case
    when lower(x) like '%casual%' then 'casual'
    when lower(x) like '%member%' or lower(x) like '%annual%' then 'member'
    end;

-- Subway station name to a matching key: upper case, no "Station", punctuation or line
-- qualifiers. Delay names are hand-typed and cut at 22 characters, so they get the same
-- treatment and are then matched exactly, by alias, or as a unique prefix.
create or replace macro station_key(x) as trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
    -- "YONGE SHP" is the Line 4 platform at Sheppard-Yonge, not Bloor-Yonge's Yonge.
    regexp_replace(upper(x), '\bYONGE[ -]*(SHP|SHEP)\b', 'SHEPPARD YONGE'),
    '\(.*$', ''),                                                     -- "(ENTERING ..." notes
    '\b(STATION|STATIO|STATI|STAT|STA|STN|SATION|STATON|STAION|BD|YUS|YU|SRT|SHP|LINE [1-4])\b', ' ', 'g'),
    '[^A-Z0-9 ]', ' ', 'g'),                                          -- . ' - / and the like
    '\s+', ' ', 'g'));

create or replace macro subway_line(x) as case regexp_replace(upper(coalesce(x, '')), '[^A-Z0-9/]', '', 'g')
    when 'YU' then '1' when 'YUS' then '1' when '1' then '1'
    when 'BD' then '2' when 'B/D' then '2' when '2' then '2'
    when 'SRT' then '3' when '3' then '3'
    when 'SHP' then '4' when '4' then '4'
    when '' then null
    else case when x like '%/%' then 'multi' end
    end;
