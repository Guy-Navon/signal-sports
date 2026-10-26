# #353 before/after: every changed decision, reproducible

Generated 2026-10-26 from **isolated data**, not from the historical feed:
- a frozen, verified copy of the corpus (`scripts/backup_db.py`, 2026-10-25 20:01 JST, sha256 `4a7cb5f8…a7a2`, 3,307 articles);
- `scripts/corpus_rerun_diff.py snapshot` run on it twice, with `main` (74541ab) and with this branch.

Both snapshots are **rules only**: no LLM, no translation and 0 model calls. That is the deterministic approximation of production. Stored LLM facts would still differ for some rows.

- The 35 holdout rows are excluded. 1 holdout row also flips; it is not shown.
- Ratings are looked up only for non-holdout ids, from census #2, N05, the week sample and the focused set.
- The original rating files are unchanged.

| | |
|---|---|
| Decision flips (non-holdout) | **29**: all for Guy; the Deni fan is unchanged on every row |
| Already rated by the owner | 13 (see the last column) |
| Unrated | **16**, served blind for rating (`people_259_flips_sample.json`, `rate_census.py serve`; the page shows no decision) |
| New push | 1 (Lundberg, walla 07-23). See BASKETBALL_PEOPLE_259.md |

**Reading the columns:**
- **facts change**: what the rules produce differently. `sport unknown→basketball` means a person proved the sport, and then the club named in the text could resolve.
- **people resolved**: the club people (and executives) the branch's resolver finds in the title, and separately in the subtitle. A person found only in the subtitle gives the sport, not the club.
- **Guy**: the decision on `main` → the decision on this branch, for the `guy` seed profile, Preference V2.

Reproduce:

```
python scripts/backup_db.py <copy.db>
python scripts/corpus_rerun_diff.py snapshot --db <copy.db> --out main.json      # on main
python scripts/corpus_rerun_diff.py snapshot --db <copy.db> --out pr.json        # on this branch
python scripts/corpus_rerun_diff.py compare main.json pr.json --ratings ../docs/qa/census2_ratings.json
```

| date | source | title | Guy | Deni fan | facts change | people resolved | owner rating (Guy) |
|---|---|---|---|---|---|---|---|
| 2026-07-10 | sport5_sport | [שכרו בפנים: בלייקני האריך חוזה בהפועל](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=551758) `rss_1ce6e0cb000807718c6d` | hidden→**feed** | = | +team:hapoel_tlv_bb | title: אנטוניו בלייקני | unrated |
| 2026-07-11 | sport5_sport | [מדר: "עוזב בראש מורם. השנה לא הייתה קלה"](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=551888) `rss_c822881b1744b3a03cd1` | hidden→**high** | = | +team:maccabi_tlv_bb | title: ים מדר | unrated |
| 2026-07-11 | walla_sport | [אף מילה על הבעלים והמאמן: כך ים מדר נפרד מהפועל ת"א](https://sports.walla.co.il/item/3852704) `rss_b00872cb282e17b00a9b` | hidden→**high** | = | sport unknown→basketball; +team:maccabi_tlv_bb,team:hapoel_tlv_bb | title: ים מדר | unrated |
| 2026-07-11 | ynet_sport | [ים מדר נפרד מהפועל ת"א: "השנה לא הייתה קלה עבורי, עוזב בראש מורם"](https://www.ynet.co.il/sport/israelibasketball/article/hyoojsxezx) `rss_136180b819765f140420` | feed→**high** | = | +team:maccabi_tlv_bb | title: ים מדר | unrated |
| 2026-07-12 | sport5_sport | [נקבע: מתי ים מדר ישחק נגד הפועל ת"א](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=551981) `rss_bbaad279d47c35547eec` | low→**feed** | = | +team:maccabi_tlv_bb | title: ים מדר | unrated |
| 2026-07-12 | walla_sport | [כבר באמצע ספטמבר: ים מדר יפגוש את הפועל תל אביב](https://sports.walla.co.il/item/3852955) `rss_219b6a536e99f26120ea` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb,team:hapoel_tlv_bb | title: ים מדר | unrated |
| 2026-07-12 | walla_sport | [החמישי בהיסטוריה של ת"א: ים מדר חצה את הכביש, והאדמה רועדת](https://sports.walla.co.il/item/3851005) `rss_3c44dfdc17c8693719c6` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: ים מדר | unrated |
| 2026-07-13 | sport5_sport | [פגישה על הפרק: מו"מ הפועל וג`ייקוב טופין](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=552027) `rss_a7ae4219580633a2661c` | hidden→**feed** | = | +team:hapoel_tlv_bb | title: ג'ייקוב טופין | unrated |
| 2026-07-16 | sport5_sport | [בר טימור במשא ומתן על חוזה חדש בהפועל](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=552397) `rss_a7850f04c198390451cf` | hidden→**feed** | = | +team:hapoel_tlv_bb | title: בר טימור | low (N05) |
| 2026-07-16 | sport5_sport | [הסיפור המלא נחשף: מאחורי עסקת מדר למכבי](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=552402) `rss_ad092a5e70c6a1d95920` | hidden→**feed** | = | +team:maccabi_tlv_bb | title: ים מדר | high (N05) |
| 2026-07-16 | walla_sport | [הדבר הבא: הפועל ת"א מתחזקת, מכבי ת"א מחכה וגל רביב בראיון](https://sports.walla.co.il/item/3854030) `rss_2d2a967d6d20dd437477` | hidden→**feed** | = | sport unknown→basketball; +team:hapoel_tlv_bb,team:maccabi_tlv_bb | ; subtitle: דימיטריס איטודיס | unrated |
| 2026-07-18 | walla_sport | [שבוע קריטי במו"מ עם לונדברג: "זה לא יכול להימשך עוד הרבה"](https://sports.walla.co.il/item/3854409) `rss_923be46ef9359e9fc319` | hidden→**high** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: איפה לונדברג | unrated |
| 2026-07-20 | israel_hayom_sport | [המסר עבר: הפועל תל אביב השאירה את ים מדר מאחור](https://www.israelhayom.co.il/sport/israeli-basketball/article/21019800) `rss_3e62e0930522fb242ab7` | hidden→**feed** | = | +team:maccabi_tlv_bb | title: ים מדר | unrated |
| 2026-07-23 | walla_sport | [איפה לונדברג סיכם על חוזה חדש במכבי תל אביב. סומן מחליף לווקר](https://sports.walla.co.il/item/3855583) `rss_9ccfed7f40f424ede65d` | hidden→**push** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: איפה לונדברג | unrated |
| 2026-07-23 | walla_sport | [מירוץ החימוש / השוק האירופי משתגע: מכבי, הפועל וירושלים עם אבי אבן באולפן](https://sports.walla.co.il/item/3855762) `rss_b31b2d7db1689e5a51c5` | hidden→**high** | = | sport unknown→basketball; +team:maccabi_tlv_bb | ; subtitle: רומן סורקין, ים מדר | unrated |
| 2026-09-11 | sport5_sport | [בריסט: "חשוב לנו לשחק נגד יריבות חזקות"](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=560443) `rss_14857700621166c5fd56` | hidden→**high** | = | +team:maccabi_tlv_bb | title: אושיי בריסט | feed (census#2) |
| 2026-09-11 | sport5_sport | [קולסון כיכב, 87:92 למכבי ת"א על אריס](https://www.sport5.co.il/articles.aspx?FolderID=405&docID=560427) `rss_375649c3d0de48af0673` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: בונזי קולסון; subtitle: אושיי בריסט | high (census#2) |
| 2026-09-13 | walla_sport | [חי ממשחק ההכנה: אולימפיאקוס - מכבי תל אביב 35:35 (מחצית)](https://sports.walla.co.il/item/3867425) `rss_fb056b5520fd43f52cc0` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb,team:olympiacos_bb | ; subtitle: אושיי בריסט, דניאל תייס | low (census#2) |
| 2026-09-16 | sport5_sport | [בסימן שאלה: דניאל תייס ייעדר מול הפועל ת"א?](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=560918) `rss_b7637deb3ec8fea492ef` | feed→**high** | = | +team:maccabi_tlv_bb | title: דניאל תייס; subtitle: ג'ימי קלארק | high (census#2) |
| 2026-09-16 | walla_sport | [דרבי על תואר: מכבי תל אביב והפועל תל אביב ייפגשו בסופרקאפ](https://sports.walla.co.il/item/3868343) `rss_f47fc2b99dda8605455f` | hidden→**high** | = | sport unknown→basketball; +team:hapoel_tlv_bb,team:maccabi_tlv_bb | ; subtitle: ג'ייקוב טופין | feed (census#2) |
| 2026-09-18 | sport5_sport | ["בלתי נתפס": באירופה נדהמו מהסל של ים מדר](https://www.sport5.co.il/articles.aspx?FolderID=274&docID=561080) `rss_83f40a05520d3edca884` | hidden→**feed** | = | +team:maccabi_tlv_bb | title: ים מדר | feed (census#2) |
| 2026-09-18 | walla_sport | ["אין הצהרות": מכבי ת"א מרוצה מהזכייה בסופרקאפ, אך לא נסחפת](https://sports.walla.co.il/item/3868698) `rss_9b49212690345a6153da` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb; −team:asvel | ; subtitle: אושיי בריסט, דניאל תייס, ים מדר | feed (census#2) |
| 2026-09-18 | walla_sport | ["בראינט מעניין רק את בראינט. למדר יש בייגלה מעל הראש"](https://sports.walla.co.il/item/3868743) `rss_ced6e83efda59fa746ee` | hidden→**high** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: ים מדר; subtitle: דימיטריס איטודיס, ואסיליה מיציץ' | feed (census#2) |
| 2026-09-19 | walla_sport | [הפועל תל אביב כבר מתחרטת? "יש בים מדר משהו קוסמי, זה לא רגיל"](https://sports.walla.co.il/item/3868798) `rss_92201d7c1e9c8c7b5e5b` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb,team:hapoel_tlv_bb | title: ים מדר | feed (census#2) |
| 2026-10-07 | walla_sport | [קולסון עקץ את הפועל: "כיום האוהדים שלהם קצת נעלמו"](https://sports.walla.co.il/item/3871322) `rss_d31972a957985cf8790e` | feed→**high** | = | +team:maccabi_tlv_bb; −team:olympiacos_bb | title: בונזי קולסון | high (census#2) |
| 2026-10-11 | sport5_sport | [ג`ייסון לוין בראיון בלעדי: "המטרה - להחזיר את מכבי ת"א לגדולתה"](https://www.sport5.co.il/articles.aspx?FolderID=405&docID=563328) `rss_663f44f6aab2211e0bac` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: ג'ייסון לוין | push (focused) |
| 2026-10-15 | walla_sport | [ההזדמנות שלה להיצמד לצמרת: הפועל ת"א תתארח אצל פנאתינייקוס](https://sports.walla.co.il/item/3872360) `rss_1c818946804a168af345` | hidden→**feed** | = | sport unknown→basketball; +team:panathinaikos_bb,team:hapoel_tlv_bb | ; subtitle: דימיטריס איטודיס | unrated |
| 2026-10-24 | walla_sport | [הפתעה גדולה: מכבי ראשון לציון היממה את מכבי תל אביב](https://sports.walla.co.il/item/3873515) `rss_2b8572f12342fe3f1659` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb | ; subtitle: רומן סורקין | unrated |
| 2026-10-25 | walla_sport | ["העומס עצום": מכבי תל אביב בנפילה, וקולסון מודה: "אנחנו בתקופה קשה"](https://sports.walla.co.il/item/3873570) `rss_aaaa453b3d37570afced` | hidden→**feed** | = | sport unknown→basketball; +team:maccabi_tlv_bb | title: בונזי קולסון | unrated |
