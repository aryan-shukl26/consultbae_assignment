"""
Builds the unified person database by running a matching cascade against
the 3 cleaned source files (df1_final, df2_final, df3_final):

  Tier 1: exact match — email (source1<->source2), phone (source1/2<->source3)
  Tier 2: fuzzy name+city fallback, with a conflict veto (rejects a merge if
          the candidate's email/phone actively disagrees with what's on file)
  Tier 3: match_confidence tagging (high/medium/manual_review) so every
          merge decision is traceable, not silently certain
  Tier 4: union-find consolidation pass to catch any remaining same-name
          same-city duplicates without over-merging genuine conflicts

Produces consultbae.db with person / person_source_record / skill tables.
"""

#Dependencies and Data Loading
"""

import sqlite3
import json
from collections import defaultdict
import pandas as pd
from rapidfuzz import fuzz

# load your actual final cleaned files
df1_final = pd.read_csv('data/df1_final.csv')
df2_final = pd.read_csv('data/df2_final.csv')
df3_final = pd.read_csv('data/df3_final.csv')

print(df1_final.shape, df2_final.shape, df3_final.shape)
print(df1_final.columns.tolist())
print(df2_final.columns.tolist())
print(df3_final.columns.tolist())

"""#Exact match on Email between source1 & source2 and Phone between source1/source2↔source3"""

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

# source1 is the base — one person per dedup_group_id
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

"""#Fuzzy name + city for anyone left unmatched after step 1"""

def find_best_matches(name, city, threshold=90):
    scored = []
    for idx, p in enumerate(person_records):
        if p['canonical_name'] is None:
            continue
        score = fuzz.ratio(name.lower(), p['canonical_name'].lower())
        if city and p['city'] and city == p['city']:
            score += 5
        if score >= threshold:
            scored.append((idx, score))
    scored.sort(key=lambda x: -x[1])
    return scored

def has_conflict(candidate, email, phone):
    return (email and candidate['email'] and email != candidate['email']) or \
           (phone and candidate['phone'] and phone != candidate['phone'])

def resolve_leftover(row, email, phone, city, source_file):
    name = row['norm_name']
    candidates = find_best_matches(name, city)
    clean = [(i, s) for i, s in candidates if not has_conflict(person_records[i], email, phone)]

    if clean:
        idx, score = clean[0]
        if email and not person_records[idx]['email']:
            person_records[idx]['email'] = email
        if phone and not person_records[idx]['phone']:
            person_records[idx]['phone'] = phone
        if person_records[idx]['match_confidence'] == 'high':
            person_records[idx]['match_confidence'] = 'medium'
        add_source_record(idx, source_file, row, 'fuzzy_name_city')
        return

    if candidates:
        # every high-scoring candidate conflicts -> genuinely a different person
        idx = add_person(name, email, phone, city, 'manual_review')
        add_source_record(idx, source_file, row, 'new_person_conflict')
        return

    idx = add_person(name, email, phone, city, 'high')
    add_source_record(idx, source_file, row, 'new_person')


unmatched_s2 = df2_final[~df2_final['norm_email'].isin(s2_matched)]
unmatched_s3 = df3_final[~df3_final['norm_phone'].isin(s3_matched)]

for _, row in unmatched_s2.iterrows():
    if row['norm_name']:
        resolve_leftover(row, row['norm_email'], None, row['norm_loc'], 'gig_workers')

for _, row in unmatched_s3.iterrows():
    if row['norm_name']:
        resolve_leftover(row, None, row['norm_phone'], row['norm_city'], 'cbnexus')

print(f"Total people after fuzzy resolution: {len(person_records)}")

"""#Confidence Tagging"""

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

"""#Database Creation"""

DB_PATH = 'consultbae.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys = ON;")

cur.executescript("""
DROP TABLE IF EXISTS skill;
DROP TABLE IF EXISTS person_source_record;
DROP TABLE IF EXISTS person;

CREATE TABLE person (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT, email TEXT, phone TEXT, city TEXT,
    match_confidence TEXT, ctc INTEGER, applied_date TEXT, experience_years REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE person_source_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    source_file TEXT, raw_data TEXT, matched_on TEXT
);
CREATE TABLE skill (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES person(person_id),
    skill TEXT, source TEXT,
    UNIQUE(person_id, skill, source)
);
""")
conn.commit()

person_id_map = {}
for i, p in enumerate(person_records):
    cur.execute(
        "INSERT INTO person (canonical_name, email, phone, city, match_confidence, ctc, applied_date, experience_years) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (p['canonical_name'], p['email'], p['phone'], p['city'], p['match_confidence'],
         p.get('ctc'), p.get('applied_date'), p.get('experience_years'))
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
