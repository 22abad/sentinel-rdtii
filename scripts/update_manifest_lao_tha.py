#!/usr/bin/env python3
"""Update manifest: LAO 8.4 + THA 5.3 + THA 5.4"""
import json, hashlib

MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"
entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]

# LAO 8.4
text = open("data/round2_corpus/LAO/decree-164-gov-internet-management-2012.txt").read()
sha = hashlib.sha256(text.encode()).hexdigest()
entries = [e for e in entries if not (e.get('economy')=='LAO' and e.get('indicator_id')=='8.4')]
entries.append({"economy":"LAO","law_name":"Decree on the Management and Use of Internet No. 164/Gov (2012)","indicator_id":"8.4","urls":["http://lsp.moic.gov.la"],"text_path":"data/round2_corpus/LAO/decree-164-gov-internet-management-2012.txt","status":"ok","char_count":len(text),"sha256":sha})

# THA 5.3 + THA 5.4
text2 = open("data/round2_corpus/THA/telecommunications-business-act-2544-2001.txt").read()
sha2 = hashlib.sha256(text2.encode()).hexdigest()
for ind in ["5.3","5.4"]:
    entries = [e for e in entries if not (e.get('economy')=='THA' and e.get('indicator_id')==ind)]
    entries.append({"economy":"THA","law_name":"Telecommunications Business Act B.E. 2544 (2001)","indicator_id":ind,"urls":["https://nbtc.go.th"],"text_path":"data/round2_corpus/THA/telecommunications-business-act-2544-2001.txt","status":"ok","char_count":len(text2),"sha256":sha2})

with open(MANIFEST,'w') as f:
    for e in entries: f.write(json.dumps(e,ensure_ascii=False)+'\n')
print(f"Manifest: {len(entries)} entries. LAO 8.4 + THA 5.3/5.4 done.")
