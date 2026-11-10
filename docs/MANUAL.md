# Imprint manual

Imprint has three tabs: **Notebook**, where you work; **Kits**, where your brands live; and **Storage**, where
you see and delete what Imprint keeps.

The Notebook has three panes, left to right: your **Sources**, a **Chat** about them, and the **Studio**, where you
make things from them.

## 1. Add your sources (left pane)

- **File** adds a PDF, a Word file (.docx), a text or Markdown file, or a transcript (.vtt, .srt or .txt). Up to
  25 MB each. You can also drop files onto the pane. A scanned PDF with no text layer, a password-protected PDF or
  an old .doc file is refused with what to do instead.
- **Link** adds a public web page. Imprint reads it through your own Hermes web tool (`web_extract`); if that isn't
  set up, it reads the page itself with Hermes's safe web client. Addresses on your own computer or network are
  refused before anything is sent.
- **Paste** adds text you copy from anywhere, with a title.

Imprint can't listen to audio or video. Add the transcript instead; Zoom, Teams, Otter and YouTube all export one.

Each source shows its title, its kind, its size and, a few seconds after it is read, a two-sentence summary written
by your model. Click the summary to read all of it. **Untick** a source to leave it out: the chat answers only from
ticked sources, and the Studio builds only from them. **Use every source** ticks them all.

Click a source's title to open it in the pane: every passage with its place (a page, a heading, a timestamp).
**All sources** goes back.

## 2. Ask (middle pane)

Before you ask anything, the chat shows what your ticked sources are and questions they can answer. Click one, or
type your own and press **Ask** (Enter sends; Shift+Enter adds a line).

Answers bring the sources together and number every claim. Each number opens the passage it came from in the left
pane, highlighted. Under the answer, the numbered list names each source and its place. A number appears only when
it points to a real passage your model was shown from a ticked source; anything else is dropped.

- **Pin as note** keeps the answer, with its citations, in the Studio's Notes.
- **Copy** copies the answer without the numbers.
- The questions under the latest answer are follow-ups your sources can answer.
- **Clear the chat** (two clicks) deletes the conversation; notes you pinned stay.

## 3. Make something (right pane)

1. The **Kit** at the top is the brand everything is set in. Open it to pick a studio kit, one of your own, or an
   earlier starter; **Import a brand kit** and **Build your own** go to the Kits tab.
2. Pick what to make: **Slide deck**, **Graphic**, **Audio brief** or **One-pager**.
3. Under **What is it for**, say who it's for and what it should do ("A short deck for the April 8 budget work
   session"). **Build around N pinned notes** puts your notes in the brief as the points to lead with; facts still
   come only from the sources. For a deck, **Ask my Hermes image tool for a picture slide** lets the model request one
   photograph; leave it off and a picture slide is set as type.
4. Press **Make**. The Studio shows each step as it happens, with how long it took. When it's done, the result opens
   in the viewer.

What each makes:

- **Slide deck**: a title slide, 7 to 10 slides and a sources slide, composed in the kit's deck system: section
  openers, content, a big number, a quote, an exhibit (a bar chart labeled directly, with its source at the foot), a
  comparison, a timeline, a picture slide and a closing slide. Reading text is 30 pt or larger; chart labels 20 pt or
  larger; only source lines and slide numbers are smaller. Exports as PowerPoint and PDF.
- **Graphic**: one information graphic, 4:5, that carries one message: a headline that states it, one chart (bars,
  headline figures, a two-way comparison or a timeline) labeled where the values sit, a takeaway line and the source
  line. Exports as PNG, SVG and PDF.
- **Audio brief**: a spoken script for one narrator, recorded by your Hermes voice. (Hermes's voices give one narrator;
  a two-voice conversation needs separate voices, which Hermes's text to speech doesn't offer to plugins today.)
  Exports the recording, the script and a script PDF.
- **One-pager**: one printed page in the kit's page layout. Exports as PDF, a proof PDF with crop marks, and HTML.

**Made in this notebook** lists everything you've made; click one to open it. **Notes** holds pinned answers and
lines you add with **Add a note**; remove one with its x.

### The viewer

The output opens large over the chat and the Studio, with its checks above it. **Set it in another kit** (the menu)
redoes the wording in that kit's voice and keeps every fact. **Export** saves a file where you choose. **Delete** takes
two clicks. **Back to chat** or Escape closes it.

## 4. Read the checks

Under each proof is a row of checks. Click one to see the detail.

- **Numbers and quotes.** Every number and quoted phrase is matched to a passage in your sources. A quote matches
  whatever punctuation ends it, a number written out in the source ("sixty-eight percent") matches the digits, and
  a number from your own request ("a 90-second brief") counts as yours. If the model cited the wrong passage but
  the number is in another one, Imprint corrects the citation (listed in one line you can open). If a number or
  quote isn't in your sources at all, it is listed first as "not found in sources" and export is blocked. Each one
  shows the closest sentence from any of your sources; choose **Fix the wording**, **Remove it**, or **Keep it,
  I checked**. Keeping it is recorded.
- **Contrast.** Every text color is measured against the color behind it. Brand colors too light for text are kept
  to rules and fills.
- **Never-say words** from the kit's voice rules are swapped out or flagged.
- **Required lines** (a disclaimer, a funder credit) must be present. Your own kit's lines print on everything
  unless you open this check and press **Leave it off this output**. A starter kit's lines (Docket's "Not legal
  advice.") print only when you press **Add it to this output**.
- **Logo.** If your logo would vanish on the band or the paper, Imprint uses your reversed logo there, or sets the
  parts that would vanish in the band's text color, and says so here.
- **Fonts.** If a kit's font can't be used, the check and the colophon say what was set in its place.
- **Length** (audio only) reads the script at 150 words a minute, against the length you asked for ("a
  90-second brief"), or two to four minutes.

The check proves a number is in your sources. It can't tell whether the source itself is right.

## 5. Export

Press **Export** above a proof and pick a format. Your computer's save dialog opens; the file goes where you pick.

| Output | Formats |
|---|---|
| One-pager | PDF, Proof PDF with crop marks, HTML page |
| Deck | PowerPoint (.pptx), PDF of the slides |
| Audio brief | Audio file, Script (text), Script PDF |

The finished files are ready to send: the colophon ("Set in ...") and the kit's color bar print only on the
**Proof PDF**. The HTML page fits a phone and its source marks link to the source list. If the kit's **Source
list** is off (a menu, a flyer), no source marks print on any export; the proof still shows every trace.

The PowerPoint carries the kit on its slide master: theme colors, theme fonts, the paper color and the logo. Every
slide is built on a real layout with its heading in the title placeholder, so outline view, Designer and the
accessibility checker work. The speaker notes list the sources behind each slide. Send the PDF too if the people
you send it to don't have the kit's fonts.

## 6. Audio briefs

The script is written for one narrator: short sentences, signposts and a recap. It is spoken by your own Hermes
voice (Settings, text to speech). The kit's delivery notes ("Plain, steady, unhurried") go along as instructions;
OpenAI voices follow them, other voices ignore them.

If your Hermes voice isn't set up, the script is still made and ready to read or export. Turn on text to speech,
then press **Record again**. A recording that takes longer than five minutes stops and offers Record again.

## 7. Kits

The Kits tab shows your kits, the five **studio kits**, and the earlier starters (one click to list them). Each studio
kit shows its own title slide and exhibit, so you judge it by what it makes. **Use in the Studio** makes it the
Studio's kit. Click a kit to open it on the bench.

The studio kits, each built on one studio method:

- **Counsel**: the consulting exhibit. Every slide title is the conclusion in a sentence, a tracker names the section,
  one bar is highlighted, a source line sits on every slide. Source Serif 4 over Source Sans 3; navy, teal.
- **Chart Room**: the data desk. A red tab over every headline, a standfirst that says what is measured, charts on
  gridlines in two colors. Public Sans over Source Serif 4; newsprint white, tab red, data blue.
- **Stage**: the keynote. A dark ground, one idea a slide, very large type, numbers given the whole slide in amber,
  pictures full bleed. Inter.
- **Folio**: the book. Generous margins, centered openers with the part in words, a running head and folios, quotes
  set as an epigraph. Libre Caslon Display over Crimson Pro; book paper, bottle green.
- **Meridian**: the modernist poster. A twelve-column grid, flush-left type, rules that divide, condensed figures,
  whole fields of ultramarine. Barlow and Barlow Condensed.

### The bench

- **Colors.** Paper and ink, then each brand color with a role (band, head, accent, rule, fill). Each color shows
  its contrast against the paper and what that allows: text, rules only, or fills only.
- **What it makes.** The kit's slides (title, exhibit, big number, timeline, quote, closing) and its graphic on a
  built-in sample, redrawn as you edit.
- **Type and page.** Heading and body fonts, the layout (Banner, Headline, Margin rail, Letter, Bulletin, Flyer or
  menu, Report), density, **Slides and graphics** (which deck system the kit uses: Exhibit, Chart room, Stage, Folio
  or Grid; left alone, Imprint picks the one that suits the layout and ground), and the organization name printed on
  the page. Add your own font as a .ttf file. A font
  that isn't on this computer is set in the nearest open font Imprint carries, and the colophon says which.
- **Voice.** How it writes, how the narrator sounds, words it never says, and "say this, not that" pairs.
- **Every page.** Source list, page numbers, date, and required lines, one per line.
- **Logo.** An SVG, PNG or JPG. Add a **reversed logo** too if you have one (the white or knockout version); Imprint
  uses it wherever your main logo would vanish, such as on a band in your own color.

A starter kit can't be changed directly. Press **Save as my copy** to make it yours.

### Four ways to start a kit

- **Help me build a kit.** Fill in what can't change, who reads it and what they need to do, and up to three
  references (starter kits, a website you admire, or your logo or brand sheet). Press **Propose three kits**. Each
  proposal says why it fits, what it borrowed and what is new. Press **Use this kit** on the one you want. Imprint
  remembers your recent looks so the next proposals don't repeat them.
- **Build from a website.** Type an address. Imprint reads the colors and fonts from the site's own stylesheets
  and shows the result as a proof. Some sites block readers; Imprint says so and offers the manual route. It never
  tries to get around a block.
- **Import a kit.** Pick your **brand guide PDF** (Imprint reads its color codes, the words beside them and the
  fonts it names), paste color codes (copy the whole color page: names like "Harbor Teal" and notes like "Calls to
  action only" set the roles), drop a CSS file or a design-token file (Figma, Tokens Studio, Penpot), pick an Open
  Design package folder, drop a Claude Design `.zip` or pick its folder, drop a PowerPoint (in Canva: Share,
  Download, PowerPoint; colors are ranked by what your slides use), or pick a logo or brand sheet image for your
  model to read. Colors left out are listed under **Skipped**, each with **Add it back**.
- **New kit by hand.** Start from a blank kit.

Every import becomes a draft shown as a full proof of your latest one-pager. Nothing is saved until you press
**Save kit**; then the new kit becomes the Studio's kit, ready for your next make. Logos found in an import are offered, never picked for you. Imports never bring in required lines.

Use kits only for brands you own or have permission to use.

## 8. Storage tab

Lists every source and output with its size, the tokens used today on your own model, an optional daily token
limit, and the storage Imprint uses. Delete takes two clicks. **Forget everything** deletes every source, kit,
output and setting after you type "forget everything".

## When something goes wrong

| What you see | What to do |
|---|---|
| Imprint couldn't reach your Hermes model | Check the model in Settings, then press Retry. Your sources and kits are untouched. |
| The answer came back cut off | Press Retry, or ask for a shorter output. |
| Audio needs a Hermes voice | Turn on text to speech in Settings, then press Record again. |
| That site didn't let Imprint read it | Make the kit by hand or import a file instead. |
| Pick a model that can see images | Set a vision-capable model, or paste your color codes. |
| Stopped when Hermes restarted | Press Retry. |
| Not installed: (a library) | Reinstall Imprint and accept the libraries it lists. |
