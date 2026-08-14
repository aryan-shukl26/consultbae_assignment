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

# --- paste your actual Cells 1 through 7 code here ---
