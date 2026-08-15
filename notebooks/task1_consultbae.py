# -*- coding: utf-8 -*-
"""Task1_Consultbae.py"""

# !pip install rapidfuzz (Removed as per requirements)

import pandas as pd
import re
import json
import sqlite3
from datetime import datetime
from collections import defaultdict

df1 = pd.read_csv('/content/drive/MyDrive/consultbae_assignment/source1_naukri_applicants.csv')
df2 = pd.read_csv('/content/drive/MyDrive/consultbae_assignment/source2_gig_workers.csv')
df3 = pd.read_csv('/content/drive/MyDrive/consultbae_assignment/source3_cbnexus_contacts.csv')

print(df1.shape, df2.shape, df3.shape)

# Null/Empty row handling
df2.dropna(inplace=True)
df3 = df3.drop(index=14).reset_index(drop=True)

print(df1.shape, df2.shape, df3.shape)

# Normalization functions
def normalize_email(email):
    return str(email).strip().lower() if pd.notna(email) else None

def normalize_phone(phone):
    """Strip everything down to a bare 10-digit Indian number."""
    if pd.isna(phone):
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits if len(digits) == 10 else None

CITY_MAP = {
    'gurugram': 'gurgaon',
    'delhi ncr': 'delhi',
    'new delhi': 'delhi',
    'bengaluru': 'bangalore',
}

def normalize_city(city):
    if pd.isna(city):
        return None
    return CITY_MAP.get(str(city).strip().lower(), str(city).strip().lower())

def normalize_name(name):
    return re.sub(r'\s+', ' ', str(name).strip()).title() if pd.notna(name) else None

def normalize_status(status):
    return str(status).strip().lower() if pd.notna(status) else None

def normalize_verified(v):
    return str(v).strip().lower() in ('y', 'yes') if pd.notna(v) else None

def normalize_rate(rate_str):
    s = str(rate_str).strip().lower()
    if '/hr' in s:
        return float(s.replace('/hr', '')), 'hourly'
    if 'k/month' in s:
        return float(s.replace('k/month', '')) * 1000, 'monthly'
    return None, None

def normalize_ctc(ctc):
    if pd.isna(ctc):
        return None
    try:
        val = float(ctc)
    except (ValueError, TypeError):
        return None
    if val < 1000:
        return round(val * 100000)
    return round(val)

def normalize_applied_date(date_str):
    if pd.isna(date_str):
        return None
    s = str(date_str).strip()

    known_formats = ['%d-%m-%Y', '%Y-%m-%d', '%d %b %Y', '%m/%d/%Y']
    for fmt in known_formats:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    try:
        return pd.to_datetime(s, dayfirst=True).strftime('%Y-%m-%d')
    except Exception:
        return None

# Source1 cleaning and handling
df1_final = df1.assign(
    norm_name=df1['Full Name'].apply(normalize_name),
    norm_email=df1['Email'].apply(normalize_email),
    norm_phone=df1['Phone'].apply(normalize_phone),
    norm_city=df1['City'].apply(normalize_city),
    norm_ctc=df1['Current CTC'].apply(normalize_ctc),
    norm_applied_date=df1['Applied Date'].apply(normalize_applied_date),
)[[
    'norm_name', 'norm_email', 'norm_phone', 'norm_city',
    'norm_applied_date', 'norm_ctc', 'Skills', 'Experience (Years)'
]]

dupes = df1_final[
    df1_final.duplicated(subset=['norm_email', 'norm_phone'], keep=False) &
    df1_final['norm_email'].notna()
]
print("Duplicate rows found:")
print(dupes[['norm_name', 'norm_email', 'norm_phone']])

before = len(df1_final)
df1_final = df1_final.sort_values('norm_name', key=lambda s: s.str.len(), ascending=False)
df1_final = df1_final.drop_duplicates(subset=['norm_email', 'norm_phone'], keep='first').reset_index(drop=True)
print(f"{before} -> {len(df1_final)} rows after removing exact duplicate")

df1_final['dedup_group_id'] = df1_final.index
phone_groups = df1_final[df1_final['norm_phone'].notna()].groupby('norm_phone')
for phone, group in phone_groups:
    if len(group) > 1:
        canonical_idx = group.index[0]
        df1_final.loc[group.index, 'dedup_group_id'] = canonical_idx
        print(f"Grouped as one person (shared phone {phone}):")
        print(group[['norm_name', 'norm_email', 'norm_phone', 'norm_city']])

df1_final['Skills'] = df1_final['Skills'].apply(
    lambda s: ', '.join(x.strip().lower() for x in str(s).split(','))
)
df1_final.to_csv('df1_final.csv', index=False)

# Source2 cleaning and handling
df2_final = df2.assign(
    norm_name=df2['worker_name'].apply(normalize_name),
    norm_email=df2['email_id'].apply(normalize_email),
    norm_loc=df2['location'].apply(normalize_city),
    norm_status=df2['status'].apply(normalize_status),
    norm_rate=df2['rate'].apply(normalize_rate),
)[[
    'norm_name', 'norm_email', 'norm_loc', 'rate', 'norm_status', 'skill_tags'
]]

df2_final = df2_final[df2_final['norm_email'].str.contains('@', na=False)].reset_index(drop=True)
df2_final[['rate_value', 'rate_type']] = df2_final['rate'].apply(
    lambda x: pd.Series(normalize_rate(x))
)
df2_final.to_csv('df2_final.csv', index=False)

# Source3 cleaning and handling
df3_final = df3.assign(
    norm_name=df3['Name'].apply(normalize_name),
    norm_phone=df3['Phone Number'].apply(normalize_phone),
    norm_city=df3['City'].apply(normalize_city),
    norm_verified=df3['Verified'].apply(normalize_verified)
)[[
    'norm_name', 'norm_phone', 'norm_city', 'norm_verified', 'Projects Completed'
]]
df3_final.to_csv('df3_final.csv', index=False)

# Matching The data
person_records = []
source_records = []

def add_person(name, email, phone, city, confidence, extra=None):
    rec = {'canonical_name': name, 'email': email, 'phone': phone,
           'city': city, 'match_confidence': confidence}
    rec.update(extra or {})
    person_records.append(rec)
    return len(person_records) - 1

def add_source_record(person_idx, source_file, raw_row, matched_on):
    source_records.append({
        'person_idx': person_idx, 'source_file': source_file,
        'raw_data': json.dumps(raw_row.to_dict(), default=str), 'matched_on': matched_on,
    })

df2_by_email = df2_final[df2_final['norm_email'].notna()].set_index('norm_email')
df3_by_phone = df3_final[df3_final['norm_phone'].notna()].set_index('norm_phone')

s2_matched, s3_matched = set(), set()
seen_groups = set()

# Exact Matches
for _, row in df1_final.iterrows():
    gid = row['dedup_group_id']
    if gid in seen_groups:
        continue
    seen_groups.add(gid)

    group_rows = df1_final[df1_final['dedup_group_id'] == gid]
    canonical = group_rows.iloc[0]
    person_idx = add_person(
        canonical['norm_name'], canonical['norm_email'], canonical['norm_phone'],
        canonical['norm_city'], 'high',
        extra={'ctc': canonical['norm_ctc'], 'applied_date': canonical['norm_applied_date'],
               'experience_years': canonical['Experience (Years)']}
    )
    for _, r in group_rows.iterrows():
        add_source_record(person_idx, 'naukri', r.drop('dedup_group_id'), 'base_file')

    email = canonical['norm_email']
    if email in df2_by_email.index:
        s2_row = df2_by_email.loc[email]
        if isinstance(s2_row, pd.DataFrame):
            s2_row = s2_row.iloc[0]
        s2_matched.add(email)
        add_source_record(person_idx, 'gig_workers', s2_row, 'email')

    phone = canonical['norm_phone']
    if phone in df3_by_phone.index:
        s3_row = df3_by_phone.loc[phone]
        if isinstance(s3_row, pd.DataFrame):
            s3_row = s3_row.iloc[0]
        s3_matched.add(phone)
        add_source_record(person_idx, 'cbnexus', s3_row, 'phone')

print(f"People from source1 base: {len(person_records)}")
print(f"source2 matched by email: {len(s2_matched)}/{len(df2_final)}")
print(f"source3 matched by phone: {len(s3_matched)}/{len(df3_final)}")

# Unmatched entries resolution (Fuzzy matching logic removed)
def has_conflict(candidate, email, phone):
    return (email and candidate['email'] and email != candidate['email']) or \
           (phone and candidate['phone'] and phone != candidate['phone'])

unmatched_s2 = df2_final[~df2_final['norm_email'].isin(s2_matched)]
unmatched_s3 = df3_final[~df3_final['norm_phone'].isin(s3_matched)]

for _, row in unmatched_s2.iterrows():
    if row['norm_name']:
        idx = add_person(row['norm_name'], row['norm_email'], None, row['norm_loc'], 'high')
        add_source_record(idx, 'gig_workers', row, 'new_person')

for _, row in unmatched_s3.iterrows():
    if row['norm_name']:
        idx = add_person(row['norm_name'], None, row['norm_phone'], row['norm_city'], 'high')
        add_source_record(idx, 'cbnexus', row, 'new_person')

print(f"Total people after exact matches and fallback: {len(person_records)}")

# Final match check before consolidation
def union_find_merge():
    groups = defaultdict(list)
    for i, p in enumerate(person_records):
        groups[(p['canonical_name'], p['city'])].append(i)

    parent = list(range(len(person_records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                if not has_conflict(person_records[a], person_records[b]['email'], person_records[b]['phone']):
                    union(a, b)

    clusters = defaultdict(list)
    for i in range(len(person_records)):
        clusters[find(i)].append(i)

    merged, remap = [], {}
    for root, members in clusters.items():
        rec = dict(person_records[members[0]])
        for m in members[1:]:
            for field in ('email', 'phone'):
                if not rec[field] and person_records[m][field]:
                    rec[field] = person_records[m][field]
            if rec['match_confidence'] == 'high' and person_records[m]['match_confidence'] != 'high':
                rec['match_confidence'] = 'medium'
        new_idx = len(merged)
        merged.append(rec)
        for m in members:
            remap[m] = new_idx
        if len(members) > 1:
            print(f"Consolidated {len(members)} entries -> '{rec['canonical_name']}' ({rec['city']})")
    return merged, remap

person_records, remap = union_find_merge()
for sr in source_records:
    sr['person_idx'] = remap[sr['person_idx']]

print(f"\nFinal person count: {len(person_records)}")

# Unified Database creation
DB_PATH = 'consultbae.db'

conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON;")

cur.executescript("""
DROP TABLE IF EXISTS skill;
DROP TABLE IF EXISTS person_source_record;
DROP TABLE IF EXISTS person;

CREATE TABLE person (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    match_confidence TEXT,
    ctc INTEGER,
    applied_date TEXT,
    experience_years REAL,
    skill_category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE person_source_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    source_file TEXT,
    raw_data TEXT,
    matched_on TEXT
);

CREATE TABLE skill (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    skill TEXT,
    source TEXT,
    UNIQUE(person_id, skill, source)
);
""")
conn.commit()

person_id_map = {}
for i, p in enumerate(person_records):
    cur.execute(
        """
        INSERT INTO person (
            canonical_name, email, phone, city, match_confidence,
            ctc, applied_date, experience_years
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            p['canonical_name'], p['email'], p['phone'], p['city'], p['match_confidence'],
            int(p['ctc']) if pd.notna(p.get('ctc')) else None,
            p.get('applied_date'),
            float(p['experience_years']) if pd.notna(p.get('experience_years')) else None,
        )
    )
    person_id_map[i] = cur.lastrowid
conn.commit()

for sr in source_records:
    cur.execute(
        "INSERT INTO person_source_record (person_id, source_file, raw_data, matched_on) VALUES (?, ?, ?, ?)",
        (person_id_map[sr['person_idx']], sr['source_file'], sr['raw_data'], sr['matched_on'])
    )
conn.commit()

cur.execute("SELECT match_confidence, COUNT(*) FROM person GROUP BY match_confidence")
print("By confidence:", cur.fetchall())
cur.execute("SELECT COUNT(*) FROM person")
print("Total people:", cur.fetchone()[0])

# Skills addition
def insert_skills(df, skill_col, email_col, phone_col, source_label):
    count = 0
    for _, row in df.iterrows():
        email = row.get(email_col) if email_col else None
        phone = row.get(phone_col) if phone_col else None
        if phone is not None:
            phone = str(int(phone)) if pd.notna(phone) else None

        idx = next((i for i, p in enumerate(person_records)
                    if (email and p['email'] == email) or (phone and p['phone'] == phone)), None)
        if idx is None:
            continue
        pid = person_id_map[idx]

        raw = row.get(skill_col)
        for s in (str(raw).split(',') if pd.notna(raw) else []):
            s = s.strip().lower()
            if s:
                cur.execute(
                    "INSERT OR IGNORE INTO skill (person_id, skill, source) VALUES (?, ?, ?)",
                    (pid, s, source_label)
                )
                count += 1
    return count

n1 = insert_skills(df1_final, 'Skills', 'norm_email', 'norm_phone', 'naukri')
n2 = insert_skills(df2_final, 'skill_tags', 'norm_email', None, 'gig_workers')
conn.commit()

print(f"Inserted skill rows — naukri: {n1}, gig_workers: {n2}")
cur.execute("SELECT COUNT(*) FROM skill")
print("Total skill rows:", cur.fetchone()[0])
cur.execute("SELECT source, COUNT(*) FROM skill GROUP BY source")
print("By source:", cur.fetchall())
conn.close()
print("Database saved:", DB_PATH)

# Final check for pipeline
verify_conn = sqlite3.connect(DB_PATH)
verify_cur = verify_conn.cursor()

print("=" * 60)
print("PIPELINE VERIFICATION")
print("=" * 60)

verify_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = sorted(r[0] for r in verify_cur.fetchall())
expected_tables = {'person', 'person_source_record', 'skill'}
print(f"\nTables present: {tables}")
assert expected_tables.issubset(set(tables)), \
    f"MISSING TABLES: {expected_tables - set(tables)}"

verify_cur.execute("SELECT COUNT(*) FROM person")
person_count = verify_cur.fetchone()[0]
verify_cur.execute("SELECT match_confidence, COUNT(*) FROM person GROUP BY match_confidence")
confidence_breakdown = dict(verify_cur.fetchall())
print(f"\nTotal people: {person_count}")
print(f"By confidence: {confidence_breakdown}")

verify_cur.execute("""
    SELECT person_id, skill, source, COUNT(*) c
    FROM skill GROUP BY person_id, skill, source HAVING c > 1
""")
skill_dupes = verify_cur.fetchall()
print(f"\nDuplicate skill rows: {len(skill_dupes)}")
assert len(skill_dupes) == 0, f"FOUND DUPLICATE SKILLS: {skill_dupes[:5]}"

verify_cur.execute("SELECT ctc FROM person WHERE ctc IS NOT NULL LIMIT 1")
sample_ctc = verify_cur.fetchone()
if sample_ctc:
    assert isinstance(sample_ctc[0], (int, float)), \
        f"CTC not stored as a number — got {type(sample_ctc[0])}: {sample_ctc[0]!r}"
    print(f"\nSample CTC value: {sample_ctc[0]} (type OK)")

verify_cur.execute("""
    SELECT COUNT(*) FROM person_source_record psr
    LEFT JOIN person p ON psr.person_id = p.person_id
    WHERE p.person_id IS NULL
""")
orphaned_source_records = verify_cur.fetchone()[0]
print(f"\nOrphaned source records: {orphaned_source_records}")
assert orphaned_source_records == 0, "FOUND SOURCE RECORDS POINTING AT NONEXISTENT PEOPLE"

verify_conn.close()

print("\n" + "=" * 60)
print(f"✅ PIPELINE SUCCESSFUL — {person_count} people, "
      f"{sum(confidence_breakdown.values())} confidence-tagged,")
print("=" * 60)
