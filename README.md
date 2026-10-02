# Whiskers

An investment tracker for one person's Stocks and Shares ISA, split across Freetrade and
Trading 212. It shows what you hold against what you meant to hold, warns when a sleeve,
a company or a platform goes past a limit you care about, and keeps a set of warning
lights on the AI trade, next to the plan you wrote while things were calm.

It runs on your own PC. It reads from Trading 212 with a key that cannot trade, reads
Freetrade from the activity file you export, and fetches public market prices. Nothing
about your portfolio is sent anywhere.

It is not financial advice. Every figure it shows is arithmetic on your own holdings and
your own rules.

## Setting it up

1. **Unzip it somewhere outside OneDrive**, for example `Documents\Whiskers`. A syncing
   folder can lock files halfway through a build.
2. **Build it.** Double-click `build\build_windows.bat`. It sets up a private Python
   environment, runs the checks (about 190 tests), builds `dist\Whiskers\Whiskers.exe`
   in a few minutes, and puts a Whiskers shortcut on your desktop. You need Python 3.10 or newer from python.org, with "Add Python to
   PATH" ticked when you install it.
   To try it without building, double-click `Start Whiskers.bat` instead.
3. **Open it, and load your plan.** On the Welcome screen choose *Load a plan file* and
   pick `Allan's plan.json`. That sets up your 13 sleeves and their targets, the Alphabet
   rule (trim back to 8% once it passes 9.3% held directly), GOOGL and GOOG as one company,
   XPO, GXO and RXO as one freight theme, and both platforms.
   It also fixes Ouster's price symbol: Trading 212 still calls it CLA.
4. **Connect Trading 212.** In Trading 212, switch to your Stocks ISA, go to Settings,
   then API, and generate a key. Tick only the permissions that read: Account data,
   Portfolio, History and Metadata. Leave *Orders - Execute* and *Pies - Write* unticked,
   because Whiskers never trades and has no code that could. Copy the key and the secret,
   since the secret is shown only once. In Whiskers, go to Settings, choose *Connect* on
   the Trading 212 ISA, and paste both. Order history loads slowly (Trading 212 allows six
   requests a minute), so give the first sync a few minutes.
5. **Import Freetrade.** Export your activity history from the Freetrade app as a CSV.
   In Whiskers, go to Settings, choose *Import activity file* on the Freetrade ISA, and
   pick the file. Then type the cash Freetrade shows into the cash box. Whiskers offers
   an estimate, but only uses a figure you confirm.
6. **Sort holdings into sleeves.** The Allocation screen lists anything not yet in a
   sleeve, each with a suggestion. Check them and save.
7. **Set the AI share for your funds.** A single AI company counts 100% and gold counts
   0%, but a fund counts for the part of it that rides on AI. Open each fund on the
   Holdings screen and give it a share: add up the fund factsheet's weights in AI-linked
   companies (Nvidia, Microsoft, Alphabet, Amazon, Meta, Broadcom, TSMC and so on).
   Until a fund has one, the AI watch screen names it and leaves it out rather than
   counting it as zero.
8. **Write your plan.** On the AI watch screen there are two boxes: what you will do if
   the AI trade turns, and what you will do in any big fall. They appear at the top, in
   red, when the lights turn.

## Using it

- **Refresh** (bottom of the sidebar) syncs Trading 212 and fetches the latest prices.
  It also runs by itself each time Whiskers opens.
- **Freetrade** has no connection, so re-import its activity file now and then; monthly
  is plenty. Importing the same rows twice changes nothing. If a share count ever
  disagrees with Freetrade, for example after a transfer or a stock split, correct it
  on the holding's screen. The correction survives later imports.
- **When Freetrade's file is wrong.** The export leaves out shares that arrived by
  transfer and holdings changed by a corporate action, such as a fund merger. Open the
  holding on the Holdings screen and use **Correct** (type the share count Freetrade
  shows) or **No longer held**. The correction sets the holding from that day on, so
  later trades in the file build on it and re-importing never undoes it.
- **Hide amounts** blurs every pound figure, for screen sharing. Percentages stay visible.
- **Treasury bills.** Freetrade's 28-day bills each have their own ISIN, and its export
  lists every purchase but never the maturity. Whiskers recognises a bill by its name,
  drops it once it has matured (the date in its name, or five weeks after purchase when
  the name has none), and counts a live one at cost in your Cash sleeve. No price feed
  publishes bill prices, so none is asked.

## Cash and cards outside the ISAs

Settings has a **Cash and cards** section. Add bank and savings accounts (HSBC, Spring)
and credit cards (Amex, Barclaycard), and type each balance in when it changes. For a
card, type what you owe. They sit beside the portfolio: the Overview shows your cash
accounts less what's owed on cards, and they never change a sleeve's percentage unless
you tick **Part of my plan** on a cash account. Each cash account is checked against the
£120,000 of FSCS deposit protection per banking licence; cards aren't.

**Monzo can update itself.** Monzo is the only one of these with an API a person can use
for their own account. On the Monzo row, press **Connect automatically** and follow the
steps: you create a private client for yourself at developers.monzo.com, Monzo emails you
a sign-in link, and you approve the request in the Monzo app. After that, every Refresh
reads your balance (current account plus pots). Whiskers only reads; it cannot move money.
HSBC, Barclays, Barclaycard, American Express and Spring can only be reached through Open
Banking companies that need a licence and a business contract, so those are typed in.

## Market watch and your playbook

The **Market watch** screen puts markets in general first and the AI trade second, and
adds the playbook from Investments 2:

- **Your signals:** the eight triggers from the workbook, each firing or not. Five are
  fetched: the US 10-year yield, the UK 10-year gilt yield, the junk-bond spread, the
  VIX, and breadth since your baseline (2 September 2026). Three you fill in after each
  earnings season: hyperscaler capex guidance, Nvidia's data-centre growth, and the
  Magnificent Seven's share of the S&P 500. The count gives the tier: 0-1 normal, 2-3
  elevated, 4 or more structural.
- **Your ladder:** how far today's holdings sit below their high, and what that means
  for deploying cash, rung by rung.
- **The warning lights:** trend and fall-from-high lights for world shares and for the
  AI trade, plus the VIX and credit stress.

Your plan file carries the thresholds and your own action for each signal, so they are
changed in one place.

Every light is judged on a 5-day average, so a single bad day can't turn it, and each one
says how long it has been that colour and whether it improved or worsened over the past
month. A fourth group, **The economy and money**, adds slower gauges of a downturn
building: the US yield curve, the Sahm recession indicator, the St. Louis Fed financial
stress index and the investment-grade credit spread. Each group ends with a short note
on what it is saying, and the Overview's **The big picture** pulls the AI trade, markets
and the economy, and what it all means for your portfolio into three paragraphs.

## Each holding against its target

Below the sleeves, the Allocation screen lists every holding against its own target,
with a band of a quarter of the target either side, exactly as the workbook's Dashboard
does. A target with nothing held says *Not held*.

## What the warnings mean

- **Sleeve drift** uses the 5/25 rule. A sleeve's band is 5 percentage points either
  side of its target, or a quarter of the target when that is smaller: a 23% sleeve may
  sit between 18% and 28%, a 2% sleeve between 1.5% and 2.5%. Past half its band a
  sleeve is amber; past the whole band it is red. *Put new money to work* on the
  Allocation screen splits a contribution so it closes the gaps without selling
  anything.
- **Company, theme and AI rules** are your own limits. When one is breached, the warning
  says how much selling would bring it back to your level. That is arithmetic on your
  rule, not a recommendation.
- **The protection limit.** FSCS protects investments up to £85,000 per person per firm
  if a platform fails and assets are missing. Your plan sets a £78,000 buffer per
  platform, as the workbook did. Each platform goes amber at 90% of its limit and red over it.
- **ISA allowance.** £20,000 a tax year across both ISAs. Trading 212's ISA is flexible,
  so money taken out can go back in the same year; Freetrade's is set as not flexible.
  Change that in Settings if Freetrade tells you otherwise.
- **AI watch.** Six lights, each describing something prices have already done: the
  Nasdaq-100 against its 200-day average, chip stocks and Nvidia against their highs,
  whether chip stocks are still beating the market, the VIX, and US credit spreads.
  Together they give a reading of Calm, Watch, Turning or Stress. None of them can
  predict a fall, and each has gone red in sell-offs that recovered within months.
  Their job is to make sure a real turn doesn't go unnoticed, and to put your own plan
  next to the evidence when it happens.

## On your Android phone

The same app runs on the phone itself, inside Termux (a Linux environment for Android),
and opens in Chrome like an app. Nothing goes through a Play Store and nothing is
shared: the phone keeps its own copy of your data.

1. Install **Termux** and **Termux:Widget** from F-Droid. The Google Play build of Termux
   is an experimental one.
2. Download `Whiskers 1.0.0.zip` to the phone. In Termux, run these, one line at a time:

       termux-setup-storage
       pkg install -y unzip
       cp ~/storage/downloads/"Whiskers 1.0.0.zip" ~/ && cd ~ && unzip -o "Whiskers 1.0.0.zip"
       bash ~/Whiskers/phone/start-whiskers.sh

   The first start installs Python, which takes a few minutes, then opens Whiskers in
   Chrome. Later starts take a couple of seconds.
3. In Chrome's menu choose **Add to Home screen** (or **Install app**). That gives
   Whiskers its own icon and window.
4. For a one-tap start, run
   `mkdir -p ~/.shortcuts && ln -sf ~/Whiskers/phone/start-whiskers.sh ~/.shortcuts/Whiskers`,
   then add the Termux:Widget widget to your home screen and tap **Whiskers**. Use it
   whenever the icon says Whiskers isn't answering: Android stops Termux now and then to
   save battery.
5. Set it up as on the PC: load your plan file from Downloads, connect Trading 212 (a
   second read-only key just for the phone is tidiest), and import the Freetrade
   activity file exported from the Freetrade app.

On the phone, other apps can reach the same local address, so Whiskers answers only
requests carrying a key that lives in its own private folder. The start-up link hands
that key to Chrome once; Chrome keeps it for Whiskers alone.

## Exporting your data

Settings has an **Export to a spreadsheet** button, under "Updates and your data". It
makes a single Excel file with everything in it:

- **Summary** — your totals, each platform, and your ISA allowance.
- **Holdings** — every holding on every platform: sleeve, shares, cost, value, gain,
  AI share and where its price came from.
- **Allocation** — every sleeve's target against what you actually hold.
- **Dividends**, **Trades** and **Cash movements** — the full history behind those
  figures, not just the last year.

It's built fresh from the same numbers the app itself shows, so it can't drift from the
screen. "Hide amounts" doesn't affect it: exporting is a deliberate request for the real
figures, for your own records, an accountant, or deeper analysis in a spreadsheet.

## Sharing with family and friends

Whiskers publishes the same way Mittens & Pence does: the source goes on GitHub, GitHub
builds the Windows and Mac apps, and every copy tells its owner when a newer version is
out. `docs/PUBLISHING.md` walks through it; in short, make a public repository called
`whiskers` under Stumpyf1Allan, put this folder on it, and run the Release workflow with a
tag matching the version number. People download from the repository's Releases page.

Don't share your own plan file: it's yours. New users answer the ten questions in
**Build a plan from questions** (Welcome screen or Settings) for a starting plan, see
why each figure was chosen, and change anything afterwards. It names kinds of
investment, never particular funds, and it isn't advice.

## Your data

Everything lives in `%LOCALAPPDATA%\Whiskers`: the database, settings, logs and the
encrypted Trading 212 key. *Open the data folder* in Settings takes you there. To back it
up, copy that folder while Whiskers is closed. Rebuilding or deleting the app folder
never touches it.

## Where prices come from

- **Share prices:** Yahoo Finance's public charts. They are free and unofficial, so a
  price can occasionally be late or missing; Whiskers says so rather than guessing.
- **Rates, credit spreads, the VIX and exchange rates:** FRED, the Federal Reserve Bank
  of St. Louis's free data service.
- **Backup source (optional):** Stooq, which since 2026 needs a free key. Settings
  explains how to get one.

A Trading 212 holding is valued by Trading 212 itself, in pounds, so it never depends on
Yahoo. A holding nobody can price shows as missing and is left out of the totals, not
counted as £0.

## New versions

A new version comes as a new zip. Unzip it into a fresh folder and run
`build\build_windows.bat` again. Your data is untouched, because it lives in
`%LOCALAPPDATA%\Whiskers`, not in the app folder.

## If something goes wrong

- **"Too many requests" from Yahoo.** Wait a few minutes and press Refresh. Settings
  shows which price series are failing and why.
- **Trading 212 says 401.** That is the key itself, not its permissions. Check you
  pasted both the key and the secret, that neither was clipped, and that the key wasn't
  regenerated since.
- **Trading 212 says 403.** A read permission is missing, or an IP restriction on the
  key is blocking this PC. Whiskers never needs *Orders - Execute*.
- **Windows Defender flags a build.** The runbook from Mittens & Pence applies: scan it
  locally with `MpCmdRun`, and submit a false positive to Microsoft if it is one.
- **A price series "not working".** Open the holding on the Holdings screen, type a
  different symbol into *Price symbol* and press *Check*: it tries the symbol without
  saving it. London listings end in `.L`.
- **Connection says "Plain Python".** It still works; the reason the browser-style
  connection didn't load is shown next to it. Send me that line if Yahoo starts refusing.
- **Anything else.** The log is in `%LOCALAPPDATA%\Whiskers\logs\whiskers.log`.

## For tinkering

- Run the tests with `python -m pytest tests -q`.
- Run with invented prices, for trying things out offline: set `WHISKERS_FAKE_MARKET=1`.
  A red banner says so across the top of every screen.
- The code is in `folio\`: `brokers` (Trading 212, Freetrade), `market` (price sources
  and storage), `engine` (valuation, allocation, rules, warning lights, ISA) and
  `web` (the local server and the interface).
