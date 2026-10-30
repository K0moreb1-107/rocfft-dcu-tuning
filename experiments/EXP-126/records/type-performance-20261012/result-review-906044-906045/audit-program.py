
import base64, collections, csv, datetime, hashlib, io, json, math, pathlib, statistics, subprocess, sys, zlib
root=pathlib.Path('/public/home/zhangkewei/zr').resolve()
d=json.loads(base64.b64decode('eyJwcmVwYXJlZCI6IHsiY29tcGxldGUiOiB0cnVlLCAic3VibWl0dGVkIjogZmFsc2UsICJyZWNvcmQiOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9yZWNvcmRzL3R5cGUtcGVyZm9ybWFuY2UtMjAyNjEwMTIiLCAicHJlcmVnaXN0cmF0aW9uIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2V4cGVyaW1lbnRzL0VYUC0xMjYvcmVjb3Jkcy90eXBlLXBlcmZvcm1hbmNlLTIwMjYxMDEyL3ByZXJlZ2lzdHJhdGlvbi5tZCIsICJoZWFkIjogIjM1MTFhZTg0ZDBlNGI1ZTNlNGU5ZDJiZGFiODFiMTQ2NzEzNzUzNzMiLCAiY29tcHV0aW5nX3NvdXJjZV90cmVlIjogImZhYWJlZGNkMjNiZTcyN2U4MzI2NGNjZDdhNmQ4YTllNWM4YWZmNDAiLCAiY29uZmlndXJhdGlvbnMiOiBbeyJ2YXJpYW50IjogImNvbXBsZXgiLCAiY29uZmlnIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2NvbmZpZ3MvZXhwZXJpbWVudHMvRVhQLTEyNi1wZXJmb3JtYW5jZS10eXBlLWNvbXBsZXgtMjAyNjEwMTItdjIuanNvbiIsICJjb25maWdfc2hhMjU2IjogImFkNmY4YmY2NTFlMzY1MzQ3NTI3NDJhYTQ4ZjcyYWUxZGI5OGIyOWNmMGNlNDg5ODdmMDAyYmM0MGMyNGNhNGIiLCAicnVuIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2V4cGVyaW1lbnRzL0VYUC0xMjYvcnVucy9FWFAtMTI2LXBlcmZvcm1hbmNlLXR5cGUtY29tcGxleC0yMDI2MTAxMi12MiIsICJjYW5kaWRhdGUiOiB7Imluc3RhbGwiOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9hcnRpZmFjdHMvaW5zdGFsbC9FWFAtMTI2LXR5cGUtY29tcGxleC0yMDI2MTAxMSIsICJzb3VyY2VfcmVwbyI6ICIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96ciIsICJzb3VyY2VfY29tbWl0IjogImQ5ZDI5YzNmMWEyM2Y1ZjY5YjIyNzUzNjcyMTcwZDA0ZmY5MWZkZTAiLCAic291cmNlX3N0YXRlIjogIntcImNvbW1pdFwiOiBcImQ5ZDI5YzNmMWEyM2Y1ZjY5YjIyNzUzNjcyMTcwZDA0ZmY5MWZkZTBcIiwgXCJyZXBvXCI6IFwiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenJcIiwgXCJzb3VyY2VcIjogXCIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96ci9yb2NtLWxpYnJhcmllcy1yb2NtLTcuMi4yL3Byb2plY3RzL3JvY2ZmdFwiLCBcInNvdXJjZV9zdGF0dXNcIjogXCJcIiwgXCJ0cmFja2VkX3N0YXRlXCI6IFwiTSBWa0ZGVFwifSIsICJsaWJyYXJ5X3NoYTI1NiI6ICI1ZWEwOGRkZmMzOGJkOTJmOWY1NGU4MmUyMzg2NGZlZjI3OGE2MmYwNmU3OTRhMzllZjUzNmQyZDZlMzhlMDc2IiwgImJ1aWxkX3Byb3ZlbmFuY2UiOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9ydW5zL0VYUC0xMjYtdHlwZS1jb21wbGV4LWJ1aWxkLTIwMjYxMDExL2J1aWxkLXByb3ZlbmFuY2UuanNvbiJ9LCAiY2FzZXMiOiAxMDMsICJwcm9jZXNzZXMiOiAzMDksICJldmVudF9pdGVyYXRpb25zIjogNTAsICJldmVudHMiOiAxNTQ1MCwgInZhbGlkYXRpb25fam9iIjogIjkwNTM2MCIsICJjb25maWdfcm9sZSI6ICJmaW5hbCBmb3IgY29tcGxleDsgY29tbWl0dGVkIHRlbXBsYXRlIGZvciBjYXBhY2l0eSwgZXhhY3QgZGVwZW5kZW5jeSByZXNvbHZlZCBkdXJpbmcgdGhpcyBiYXRjaCBzdWJtaXNzaW9uIn0sIHsidmFyaWFudCI6ICJjYXBhY2l0eSIsICJjb25maWciOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvY29uZmlncy9leHBlcmltZW50cy9FWFAtMTI2LXBlcmZvcm1hbmNlLXR5cGUtY2FwYWNpdHktMjAyNjEwMTItdjIuanNvbiIsICJjb25maWdfc2hhMjU2IjogIjY1MDM0NGVmNmY3NzYxM2Q3NWUzMTdiMGNmNzk5YzU3MTMzOGEzODhjMjlmOTUxNjA5YzQ5M2IzOGQ5YTRiZmMiLCAicnVuIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2V4cGVyaW1lbnRzL0VYUC0xMjYvcnVucy9FWFAtMTI2LXBlcmZvcm1hbmNlLXR5cGUtY2FwYWNpdHktMjAyNjEwMTItdjIiLCAiY2FuZGlkYXRlIjogeyJpbnN0YWxsIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2V4cGVyaW1lbnRzL0VYUC0xMjYvYXJ0aWZhY3RzL2luc3RhbGwvRVhQLTEyNi1zY2FsYXItc3RyaWRlLTIwMjYxMDEyLXYyIiwgInNvdXJjZV9yZXBvIjogIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyIiwgInNvdXJjZV9jb21taXQiOiAiNDIzNTY4Njg0ZmU3Mzk1MzJmODE4NzU5OGI5MjAwZjUwMGYyNjY0NSIsICJzb3VyY2Vfc3RhdGUiOiAie1wiY29tbWl0XCI6IFwiNDIzNTY4Njg0ZmU3Mzk1MzJmODE4NzU5OGI5MjAwZjUwMGYyNjY0NVwiLCBcInJlcG9cIjogXCIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96clwiLCBcInNvdXJjZVwiOiBcIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL3JvY20tbGlicmFyaWVzLXJvY20tNy4yLjIvcHJvamVjdHMvcm9jZmZ0XCIsIFwic291cmNlX3N0YXR1c1wiOiBcIlwiLCBcInRyYWNrZWRfc3RhdGVcIjogXCJNIFZrRkZUXCJ9IiwgImxpYnJhcnlfc2hhMjU2IjogIjYxMTIxZjFmOTIwN2UzMDhmNmFiZDA4NTAyZmUwYmQzNzI4NzdkZmMwMjRkNTU5MzU2M2E2YzkwYjUxZTlmMTYiLCAiYnVpbGRfcHJvdmVuYW5jZSI6ICIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96ci9leHBlcmltZW50cy9FWFAtMTI2L3J1bnMvRVhQLTEyNi1zY2FsYXItc3RyaWRlLWJ1aWxkLTIwMjYxMDEyLXYyL2J1aWxkLXByb3ZlbmFuY2UuanNvbiJ9LCAiY2FzZXMiOiAxMDMsICJwcm9jZXNzZXMiOiAzMDksICJldmVudF9pdGVyYXRpb25zIjogNTAsICJldmVudHMiOiAxNTQ1MCwgInZhbGlkYXRpb25fam9iIjogIjkwNTY2MCIsICJjb25maWdfcm9sZSI6ICJmaW5hbCBmb3IgY29tcGxleDsgY29tbWl0dGVkIHRlbXBsYXRlIGZvciBjYXBhY2l0eSwgZXhhY3QgZGVwZW5kZW5jeSByZXNvbHZlZCBkdXJpbmcgdGhpcyBiYXRjaCBzdWJtaXNzaW9uIn1dLCAicG9saWN5IjogIkZGVC1ldmVudC1zYW1wbGVzLXNpbmdsZS12MiIsICJ0b3RhbF9wcm9jZXNzZXMiOiA2MTgsICJ0b3RhbF9ldmVudHMiOiAzMDkwMCwgInN0b3BfYWZ0ZXJfYmF0Y2hfc3VibWlzc2lvbiI6IHRydWUsICJtYW5hZ2VyX3NoYTI1NiI6ICJlZGY4NWVjYWUzNGVjNDE0Y2VkMDRmNGJjZWNiYTY3MTc0M2UzY2VhZjcwOTJkYTQ4NDUxZTk4NjA5YmQ3YzNkIiwgImpvYl9lbnRyeV9zaGEyNTYiOiAiZTNkYmI2MzQxOTY1OWIxYmQ5ZjEzMTc5ZjZiOWYwMDYwYTZmYjk3NDBmYzkxMzc0NGMwMmQ1MGM4NWNmMzBjMyIsICJ0b29sc19zaGEyNTYiOiB7ImNvbW1vbi5weSI6ICI5MzY0NjI5ZmExNjcyZDkyM2YwZjU0MmUwZjRhM2I1NGQwODQ1YjJhNDkyM2FiMDBmYzNiNGVjZDhlMmM5OTc4IiwgInNhbXBsZV9jb250cmFjdC5weSI6ICJhYmRlNmNiNzM1M2RhMmE3YzFlNzRiYzIxODA0YmEzOTgyZTU2NDFlMWM2NDlmMGQxNDE5MDMyNDg2OTM2NDAxIiwgInJ1bl9zYW1wbGVzLnB5IjogIjI3NzZmODI1ZGI5OTJlYjdlZTljMDJhOGEyNDM4NzUxZWVjNzc0ZGI2MGE5M2I1N2Y0ZDUyY2E3YjIyNmFiNmEiLCAic3VtbWFyaXplX3NhbXBsZXMucHkiOiAiNzljY2IzMGEzYWY1MDY1MTc2YTljYzYxYjk5ZjNjYTA2NDJiMGMxNGU1NDE5MDg5MTg4YzJkZGVkNjhmYTljOSIsICJwbG90X3NhbXBsZXMucHkiOiAiOGY5N2Y5OWViMGViYTE3M2E2N2Y3NDI5YzBkY2JmNTI0MTVhZjdlOTZhZTVhYzgzYTJkNDk4OTRiNzcyMmIyZCIsICJmZnRfdGVzdF8xZF9zYW1wbGVzLmNwcCI6ICI2ZDQyZjFmYmY5MTcyMjkyNjJjNmJkNzkyOTk0ZmI0NGNjMjAxNzZiOGY5YTA0ZmJiYjhhMmQ0MmEyOWZhMDhkIiwgImRldmljZV9pZGVudGl0eS5jcHAiOiAiODhiN2U5MjUzYmQ3Mzc0OTE1MWVkMWVlZWUxMTkyOWU2YzEyMTc4NDI2ODJlNWYwZTA4YzE1OTE5YjM1NGJlNyJ9LCAiZGVwZW5kZW5jeV9wbGFuIjogImNhcGFjaXR5IGFmdGVyYW55IHJldHVybmVkIGNvbXBsZXggcGVyZm9ybWFuY2Ugam9iOyBubyBzdGF0dXMvcmVzdWx0cyBpbnNwZWN0aW9uIGFmdGVyIGVpdGhlciBzdWJtaXNzaW9uIiwgInByb3RlY3RlZF9zdGFibGVfbWFpbiI6ICJlNTdhNjA0OTkyZTAyMTQwYzQ5OTcwMmUxYWYwZDljYzk0M2Q2NjZlIiwgInRyYWNrZWRfc3RhdHVzIjogIk0gVmtGRlQifSwgInN1Ym1pc3Npb24iOiB7InN1Ym1pdHRlZCI6IHRydWUsICJwb2xpY3kiOiAiRkZULWV2ZW50LXNhbXBsZXMtc2luZ2xlLXYyIiwgImpvYnMiOiBbeyJ2YXJpYW50IjogImNvbXBsZXgiLCAiam9iIjogIjkwNjA0NCIsICJydW4iOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9ydW5zL0VYUC0xMjYtcGVyZm9ybWFuY2UtdHlwZS1jb21wbGV4LTIwMjYxMDEyLXYyIiwgImNvbmZpZyI6ICIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96ci9jb25maWdzL2V4cGVyaW1lbnRzL0VYUC0xMjYtcGVyZm9ybWFuY2UtdHlwZS1jb21wbGV4LTIwMjYxMDEyLXYyLmpzb24iLCAiY29uZmlnX3NoYTI1NiI6ICJhZDZmOGJmNjUxZTM2NTM0NzUyNzQyYWE0OGY3MmFlMWRiOThiMjljZjBjZTQ4OTg3ZjAwMmJjNDBjMjRjYTRiIiwgImNvbW1hbmQiOiBbIi9wdWJsaWMvc29mdHdhcmUvYXBwcy9hbmFjb25kYTMvMjAyMy4wOS9iaW4vcHl0aG9uIiwgIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL21hbmFnZS5weSIsICJtZWFzdXJlIiwgIi0tY29uZmlnIiwgIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2NvbmZpZ3MvZXhwZXJpbWVudHMvRVhQLTEyNi1wZXJmb3JtYW5jZS10eXBlLWNvbXBsZXgtMjAyNjEwMTItdjIuanNvbiIsICItLWV4ZWN1dGUiXSwgImRlcGVuZGVuY3kiOiBudWxsLCAiY2FzZXMiOiAxMDMsICJwcm9jZXNzZXMiOiAzMDksICJldmVudF9zYW1wbGVzIjogMTU0NTB9LCB7InZhcmlhbnQiOiAiY2FwYWNpdHkiLCAiam9iIjogIjkwNjA0NSIsICJydW4iOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9ydW5zL0VYUC0xMjYtcGVyZm9ybWFuY2UtdHlwZS1jYXBhY2l0eS0yMDI2MTAxMi12MiIsICJjb25maWciOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvY29uZmlncy9leHBlcmltZW50cy9FWFAtMTI2LXBlcmZvcm1hbmNlLXR5cGUtY2FwYWNpdHktMjAyNjEwMTItdjItc2VyaWFsLmpzb24iLCAiY29uZmlnX3NoYTI1NiI6ICIzMDJhNTBmYWYwYjdiZWRkZGEzMzY0ZWQ2NjEzY2UwMDNkNDdjN2VmNmQ4NDlkNTFhMjNjYTU2YTk0M2I3MDM1IiwgImNvbW1hbmQiOiBbIi9wdWJsaWMvc29mdHdhcmUvYXBwcy9hbmFjb25kYTMvMjAyMy4wOS9iaW4vcHl0aG9uIiwgIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL21hbmFnZS5weSIsICJtZWFzdXJlIiwgIi0tY29uZmlnIiwgIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2NvbmZpZ3MvZXhwZXJpbWVudHMvRVhQLTEyNi1wZXJmb3JtYW5jZS10eXBlLWNhcGFjaXR5LTIwMjYxMDEyLXYyLXNlcmlhbC5qc29uIiwgIi0tZXhlY3V0ZSJdLCAiZGVwZW5kZW5jeSI6ICJhZnRlcmFueTo5MDYwNDQiLCAiY2FzZXMiOiAxMDMsICJwcm9jZXNzZXMiOiAzMDksICJldmVudF9zYW1wbGVzIjogMTU0NTAsICJzdWJtaXNzaW9uX2NvbW1hbmQiOiBbInNiYXRjaCIsICItLXBhcnNhYmxlIiwgIi0tY2hkaXI9L3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIiLCAiLS1vdXRwdXQ9L3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9ydW5zL0VYUC0xMjYtcGVyZm9ybWFuY2UtdHlwZS1jYXBhY2l0eS0yMDI2MTAxMi12Mi9sb2dzL3NsdXJtXyVqLm91dCIsICItLWVycm9yPS9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2V4cGVyaW1lbnRzL0VYUC0xMjYvcnVucy9FWFAtMTI2LXBlcmZvcm1hbmNlLXR5cGUtY2FwYWNpdHktMjAyNjEwMTItdjIvbG9ncy9zbHVybV8lai5lcnIiLCAiLS1jcHVzLXBlci10YXNrPTgiLCAiLS1wYXJ0aXRpb249aHgxaGRub3JtYWwwMSIsICItLXRpbWU9MDM6MDA6MDAiLCAiLS1leGNsdXNpdmUiLCAiLS1ub2RlbGlzdD1mMTNyNG4xNSIsICItLWRlcGVuZGVuY3k9YWZ0ZXJhbnk6OTA2MDQ0IiwgIi9wdWJsaWMvaG9tZS96aGFuZ2tld2VpL3pyL2pvYnMvd29ya3NwYWNlX3Rhc2suc2x1cm0iLCAibWVhc3VyZSIsICIvcHVibGljL2hvbWUvemhhbmdrZXdlaS96ci9leHBlcmltZW50cy9FWFAtMTI2L3J1bnMvRVhQLTEyNi1wZXJmb3JtYW5jZS10eXBlLWNhcGFjaXR5LTIwMjYxMDEyLXYyL3N1Ym1pdC1tYW5pZmVzdC5qc29uIl19XSwgInNvdXJjZV9oZWFkIjogIjM1MTFhZTg0ZDBlNGI1ZTNlNGU5ZDJiZGFiODFiMTQ2NzEzNzUzNzMiLCAiY29tcHV0aW5nX3NvdXJjZV90cmVlIjogImZhYWJlZGNkMjNiZTcyN2U4MzI2NGNjZDdhNmQ4YTllNWM4YWZmNDAiLCAidG90YWxfcHJvY2Vzc2VzIjogNjE4LCAidG90YWxfZXZlbnRfc2FtcGxlcyI6IDMwOTAwLCAicmVzdWx0c19ub3RfY2hlY2tlZCI6IHRydWUsICJzdG9wX2FmdGVyX3N1Ym1pc3Npb24iOiB0cnVlLCAiZGVwZW5kZW5jeSI6ICJleHBsaWNpdCBzYmF0Y2ggLS1kZXBlbmRlbmN5PWFmdGVyYW55OjkwNjA0NDsgc2NoZWR1bGluZyBzdGF0ZSBkZWxpYmVyYXRlbHkgbm90IGluc3BlY3RlZCIsICJyZWNvcmQiOiAiL3B1YmxpYy9ob21lL3poYW5na2V3ZWkvenIvZXhwZXJpbWVudHMvRVhQLTEyNi9yZWNvcmRzL3R5cGUtcGVyZm9ybWFuY2UtMjAyNjEwMTIifX0='));prepared=d['prepared'];submission=d['submission']
def inside(value):
 value=pathlib.Path(value).resolve();assert value==root or root in value.parents;return value
def sha(value):return hashlib.sha256(inside(value).read_bytes()).hexdigest()
def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)
def percentile(values,f):
 values=sorted(values);at=(len(values)-1)*f;lower=int(at);upper=min(lower+1,len(values)-1)
 return values[lower]+(values[upper]-values[lower])*(at-lower)
def metrics(values):
 return dict(mean_ms=statistics.mean(values),median_ms=statistics.median(values),min_ms=min(values),max_ms=max(values),p25_ms=percentile(values,.25),p75_ms=percentile(values,.75))
def timestamp(value):return datetime.datetime.fromisoformat(value)
sys.path.insert(0,str(root/'tools/fft_measurement'))
from summarize_samples import aggregate
import common, sample_contract
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==prepared['head']
assert subprocess.check_output(['git','rev-parse','HEAD:rocm-libraries-rocm-7.2.2/projects/rocfft'],cwd=root,text=True).strip()==prepared['computing_source_tree']
assert subprocess.check_output(['git','rev-parse','main'],cwd=root,text=True).strip()==prepared['protected_stable_main']
assert sha(root/'AGENTS.md')=='c53a686c4026f5be147a0b589103b11ae9e1fb37c086fa773fa2351566573afc'
for name,digest in prepared['tools_sha256'].items():assert sha(root/'tools/fft_measurement'/name)==digest
assert sha(root/'tools/workspace_manager/manager.py')==prepared['manager_sha256']
assert sha(root/'jobs/workspace_task.slurm')==prepared['job_entry_sha256']
reference=common.reference()
result=dict(complete=True,policy=sample_contract.POLICY,jobs={},coverage=json.loads((root/'experiments/EXP-126/records/type-repair-20261011/coverage.json').read_text()),
 total_processes=0,total_samples=0,source_head=prepared['head'],protected_stable_main=prepared['protected_stable_main'])
plots={}
windows={}
for item in submission['jobs']:
 name=item['variant'];run=inside(item['run']);cfg=json.loads(inside(item['config']).read_text())
 assert sha(item['config'])==item['config_sha256']
 resolved,prov,aggregate_rows,aggregate_samples=aggregate(run)
 assert resolved==json.loads((run/'submit-manifest.json').read_text())
 assert resolved['candidate_variant']==name and resolved['policy']==sample_contract.POLICY
 assert prov['job_id']==item['job'] and prov['complete'] and prov['timing_warmups']==3 and prov['event_iterations']==50
 assert prov['tools_sha256']==prepared['tools_sha256']
 assert prov['step_gpu']==prov['measurement_gpu']=='0' and prov['gpu']['count']==1
 assert prov['host']=='f13r4n15' and prov['gpu']['arch'].split(':')[0]=='gfx936'
 env=prov['environment'];assert env['FFT_TEST_ITERS']=='50'
 assert env['ROCFFT_RTC_CACHE_READ_DISABLE']==env['ROCFFT_RTC_CACHE_WRITE_DISABLE']=='1'
 assert {k:v for k,v in env.items() if k.startswith('ROCFFT_')}=={'ROCFFT_RTC_CACHE_READ_DISABLE':'1','ROCFFT_RTC_CACHE_WRITE_DISABLE':'1'}
 if name=='capacity':
  assert cfg['resources']['dependency']==env['SLURM_JOB_DEPENDENCY']=='afterany:906044'
  assert '--dependency=afterany:906044' in json.loads((run/'submission.json').read_text())['argv']
 build=inside(root/'experiments/EXP-126/artifacts/build/measurement'/resolved['run_id'])
 assert sha(build/'device_identity')==prov['identity_binary_sha256']
 for arm,identity in prov['arms'].items():
  assert sha(identity['actual_library'])==identity['library_sha256']==resolved['arms'][arm]['library_sha256']
  assert sha(build/'fft_test_1d')==identity['binary_sha256']
  loaded=[inside(line.strip().split('=>')[-1].strip().split(' ')[0]) for line in (run/'logs'/(arm+'_ldd.txt')).read_text().splitlines() if 'librocfft.so' in line]
  assert set(loaded)=={inside(identity['actual_library'])}
  for field in ('source_commit','source_state','install','source_repo','build_provenance'):
   assert identity[field]==resolved['arms'][arm][field]
  assert subprocess.check_output(['git','-C',identity['source_repo'],'rev-parse',identity['source_commit']+'^{commit}'],text=True).strip()==identity['source_commit']
 validation=resolved['candidate_validation'];validation_run=inside(validation['validation_run'])
 for file,digest in validation['records_sha256'].items():assert sha(validation_run/file)==digest
 expected=sample_contract.schedule(resolved);entries=json.loads((run/'processes.json').read_text());assert len(entries)==len(expected)==309
 observations={};errors=[];previous_end=timestamp(prov['start'])
 for entry,wanted in zip(entries,expected):
  assert all(entry[k]==v for k,v in wanted.items()) and entry['round']==1
  assert entry['argv']==[str(build/'fft_test_1d'),str(entry['N']),'1',entry['func'],'1']
  start,end=timestamp(entry['start']),timestamp(entry['end']);assert previous_end<=start<=end<=timestamp(prov['end']);previous_end=end
  assert entry['returncode']==0 and entry['job_id']==item['job'] and entry['gpu']==prov['gpu']
  summary=list(csv.DictReader((run/entry['csv']).read_text().splitlines()));samples=list(csv.DictReader((run/entry['samples']).read_text().splitlines()))
  assert len(summary)==1 and len(samples)==50
  row=summary[0];assert row['check']=='PASS' and int(row['batch'])==1 and int(row['iters'])==50 and int(row['is_warmup'])==1
  err=float(row['err_a']);assert math.isfinite(err) and 0<=err<1e-9;errors.append(err)
  err_b=float(row['err_b']);assert (0<=err_b<1e-9) if entry['func']=='z2z_1d' else err_b==-1
  values=[]
  for index,sample in enumerate(samples,1):
   assert sample['func']==entry['func'] and int(sample['N'])==entry['N'] and int(sample['batch'])==1 and int(sample['sample_index'])==index
   value=float(sample['elapsed_ms']);assert math.isfinite(value) and value>0;values.append(value)
  stats=metrics(values);assert all(close(row[k],stats[k]) for k in ('mean_ms','min_ms','max_ms')) and close(row['per_tf_ms'],stats['min_ms'])
  key=(entry['N'],entry['func'],entry['arm']);assert key not in observations
  assert values==aggregate_samples[key]
  observations[key]=dict(stats=stats,samples_ms=values,start=entry['start'],end=entry['end'],err_a=err,err_b=err_b,
   first10_median_ms=statistics.median(values[:10]),last10_median_ms=statistics.median(values[-10:]),
   evidence={k:entry[k] for k in ('csv','samples','stdout','stderr','csv_sha256','samples_sha256','stdout_sha256','stderr_sha256')})
 saved_rows=json.loads((run/'summary.json').read_text())['rows'];csv_rows=list(csv.DictReader((run/'comparison.csv').read_text().splitlines()))
 assert len(saved_rows)==len(csv_rows)==len(aggregate_rows)==103
 recalculated=[]
 for index,(n,func) in enumerate(common.cases(resolved)):
  computed=dict(N=n,func=func,batch=1,processes_per_arm=1,events_per_arm=50,check='PASS')
  for arm in ('official','previous','candidate'):
   computed.update({arm+'_'+k:v for k,v in observations[n,func,arm]['stats'].items()})
  for arm in ('official','previous'):
   for metric in ('mean','median'):computed['speedup_'+arm+'_'+metric]=computed[arm+'_'+metric+'_ms']/computed['candidate_'+metric+'_ms']
  computed['a100_mean_ms']=reference.get((n,func))
  computed['a100_performance_mean_percent']=reference[n,func]/computed['candidate_mean_ms']*100 if (n,func) in reference else None
  for saved in (saved_rows[index],aggregate_rows[index],csv_rows[index]):
   assert set(saved)==set(computed)
   for key,value in computed.items():
    if value is None:assert saved[key] is None or saved[key]==''
    elif isinstance(value,str):assert saved[key]==value
    else:assert close(saved[key],value),(name,index,key,saved[key],value)
  values={arm:observations[n,func,arm] for arm in ('official','previous','candidate')}
  computed['observations']=values
  ca=values['candidate']['stats'];st=values['previous']['stats']
  computed['central_interval_relation_vs_stable']='faster' if ca['p75_ms']<st['p25_ms'] else 'slower' if ca['p25_ms']>st['p75_ms'] else 'overlap'
  computed['full_range_relation_vs_stable']='faster' if ca['max_ms']<st['min_ms'] else 'slower' if ca['min_ms']>st['max_ms'] else 'overlap'
  recalculated.append(computed)
  svg=run/'plots'/('%d_%s.svg'%(n,func));assert svg.is_file()
  plots[name+'/'+svg.name]=svg.read_text()
 checksums={f:sha(run/f) for f in ('preregistration.json','submit-manifest.json','provenance.json','processes.json','summary.json','comparison.csv','comparison.md','submission.json')}
 result['jobs'][name]=dict(job=item['job'],run=str(run),processes=309,event_samples=15450,all_correctness_pass=True,max_err_a=max(errors),
  gpu=prov['gpu'],host=prov['host'],start=prov['start'],end=prov['end'],rows=recalculated,
  complete=True,records_sha256=checksums,library_sha256={arm:a['library_sha256'] for arm,a in prov['arms'].items()},
  source_commit={arm:a['source_commit'] for arm,a in prov['arms'].items()},binary_sha256=prov['arms']['candidate']['binary_sha256'],
  plots_sha256={str(svg.relative_to(run)):sha(svg) for svg in sorted((run/'plots').glob('*.svg'))})
 assert len(result['jobs'][name]['plots_sha256'])==103
 result['total_processes']+=309;result['total_samples']+=15450
 windows[name]=(timestamp(prov['start']),timestamp(prov['end']))
assert windows['complex'][1]<windows['capacity'][0]
result['serial_dependency_observed']=True
result['same_gpu_between_jobs']=result['jobs']['complex']['gpu']==result['jobs']['capacity']['gpu']
assert result['same_gpu_between_jobs']
assert result['jobs']['complex']['binary_sha256']==result['jobs']['capacity']['binary_sha256']
result['candidate_comparison_scope']='same GPU, separate sequential allocations; own neighboring official/stable controls, no direct interleaving of candidates'
accounting=subprocess.check_output(['sacct','-j','906044,906045','--noheader','--parsable2','--format=JobID,State,ExitCode,Elapsed,Start,End,NodeList'],text=True).strip()
result['accounting']=accounting
for job in ('906044','906045'):
 row=next(line.split('|') for line in accounting.splitlines() if line.split('|')[0]==job);assert row[1:3]==['COMPLETED','0:0']
result['plots_sha256']={name:hashlib.sha256(content.encode()).hexdigest() for name,content in plots.items()}
print(base64.b64encode(zlib.compress(json.dumps(dict(audit=result,plots=plots),ensure_ascii=False).encode(),9)).decode(),flush=True)
