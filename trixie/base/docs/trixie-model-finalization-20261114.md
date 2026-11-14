# Trixie-malliasennuksen viimeistely — 14.11.2026

## Toteutus ja nykyisen työn säilyminen

Paikallisen `rpi-images`-työpuun Git-status ja aiemmat muutokset tarkistettiin
ennen työtä. GitHubista ei kloonattu tai kopioitu vanhempia tiedostoja niiden
päälle. Asennus-, aktivointi-, tarkistus- ja HOME/AALTO-ohjausskriptien toiminta
säilyi tavuittain ennallaan. Työssä muutettiin vain:

1. `trixie/README.md`: Trixie Full / ARM64, yleiskäyttöinen laboratoriopohja,
   ympäristöjako, 128 GB tuotanto- ja 64 GB testikortti sekä nykyiset komennot.
2. `trixie/base/README.md`: tuotantoversiot, kamerakoneen valinnainen `/opt/rpi`,
   sovellusasentimien työnjako, Git/ZIP-lähdepuu, lukitukset ja välimuistit.
3. `trixie/base/install/packages/rpi-apt.txt`: 11 todettua preview-kehitysriippuvuutta.
4. `trixie/base/config/lab314/SHA256SUMS`: kolmen nykyisen lock/contract-tiedoston
   tarkistussummat; itse lukituksia ei muutettu.
5. `trixie/base/docs/rpi-env.md`: käyttöönotto kamerakoneissa, Python 3.13,
   SPI/sarjaliikenne sekä Bashilla suoritettavat nykyiset komennot.
6. `trixie/base/docs/sci-apps.md`: pilottiasentimen suhde uuteen sovellusasentimeen.
7. `trixie/base/docs/lab314/README.md`: näkyvä linkki viimeisimpään hyväksyttyyn
   tuotantoraporttiin; vanhat epäonnistumis-/palautusraportit säilyivät.
8. Tämä viimeistelyraportti.

Säilytettävät polut ovat `/opt/conda`, `/opt/lab314`, `/opt/rpi` sekä
`/opt/sci/bin`, `/opt/sci/bin-rpi` ja `/opt/sci/lib`. Ei uusia sovelluswrappereita,
installereitä, ympäristömallia tai käynnistysjärjestystä.

## APT-lisäykset

`common-apt.txt` sisältää jo `build-essential`- ja `pkg-config`-paketit.
`rpi-apt.txt`-tiedostoon lisättiin:

```text
libcamera-dev meson ninja-build libboost-program-options-dev
libexif-dev libjpeg-dev libtiff-dev libpng-dev
libdrm-dev libx11-dev libepoxy-dev
```

Nämä ovat Scientific Imagingin nykyisen Meson-projektin ja onnistuneen
libcamera 0.8 / IMX477 -käännös-/preview-testin suorat kehitysriippuvuudet.
Boost-kehitysheaderit tulevat program-options-dev-paketin mukana.
Erillistä libboost-all-dev-, Qt-, TFLite-, Hailo-, OpenCV-C++- tai
experimental-storage-pakettijoukkoa ei lisätty varmuuden vuoksi.

Pi:n nykyisestä APT-välimuistista saatiin kaikille 11 paketille ehdokas.
`libcamera-dev` ja `python3-libcamera`: 0.8.0+rpt20261104-1 Raspberry Pi:n
`archive.raspberrypi.com/debian`-lähteestä. Debianin 0.4.0-7 näkyi vanhempana
vaihtoehtona eikä sitä pakotettu. `rpicam-apps`: 1.15.0-1, Meson: 1.7.0-1,
Ninja: 1.12.1-1+b1. APT-lähteitä, pinnejä tai versiolukituksia ei muutettu.
Nämä ovat lukutarkistuksen tuloksia, eivät puhtaan kortin tuore APT-asennus.

C++-lähteen libcamera-yhteensopivuus korjattiin aiemmassa Scientific Imaging
-tehtävässä. Sitä ei korvata vanhemman libcamera-kirjaston asentamisella.

## Lab314 ja laitteistoympäristö

Nykyistä tuotantoa luettiin ilman toiminnallisen testisarjan käynnistystä:

| Tarkistus | Tulos |
|---|---|
| Python | 3.14.10 |
| OpenCV | 5.0.0 |
| Shapely / GEOS | 2.2.0 / 3.14.1 |
| Asennetut Python-jakelut | 145 |
| Vertailu `packages.json`-sopimukseen | 145/145 samat versiot, 0 eroa |
| `/opt/rpi` | Python 3.13.13, prefix `/opt/rpi` |
| Laitemoduulien löydettävyys `/opt/rpi`:ssä | Picamera2, libcamera, cv2, RPi.GPIO, gpiod, smbus2, spidev ja serial löytyivät |

Moduulien löydettävyys ei ole GPIO/I2C/SPI/sarjaportin laitetesti.
Nykyisessä laitteessa spidev on saatavilla järjestelmän kautta; sitä ei rakennettu
uuteen Conda-ympäristöön. Puhtaan Full-kortin laitemoduulit tarkistetaan tulevassa
asennustestissä. Tässä tehtävässä ei muutettu `/opt/rpi`:n pakettijoukkoa.

Tuotannon aiempi hyväksyntä on
[103 PASS, 0 FAIL, 0 SKIP](lab314/production-final-result-20261114.md).
Spyder-/Variable Explorer-/GUI-/Bash-testit hyödynnetään tästä raportista;
niitä ei ajettu uudelleen. Vanhat T9-polut muissa raporteissa ovat säilytetyn
kehitys-/palautushistorian sijainteja, eivät nykyisen asennuksen lähtötiedostoja.

HOME/AALTO jättävät `/opt/rpi`:n edelleen oletuksena pois. Kamerakoneessa se
luodaan perusasennuksen jälkeen nykyisellä `create_rpi_env.sh`:lla, ennen
Scientific Imagingin kameraohjelmien asentamista. Vaihtoehtoinen nykyinen
`--with-cam-imgcheck POLKU` -pilottivalinta luo puuttuvan ympäristön edelleen
alkuperäisessä kohdassaan. Nykyistä ympäristöä ei poisteta tai luoda uudelleen.

## Lukitukset, GitHub ja toistettavuus

- Conda explicit -lukitus: 23 ARM64/noarch-URL:ia MD5-tarkisteineen.
- Wheel-lukitus: 144 kiinteää wheel-URL:ia SHA-256-tarkisteineen.
- Näiden sekä Conda-pipin muodostama Python-sopimus: 145 täsmäävää jakelua.
- Python 3.14.10 ja OpenCV-wheel 5.0.0.93 (`cv2` 5.0.0) ovat lukittuja.
- Uusi `SHA256SUMS` tarkistaa kolme toimitettavaa lock/contract-tiedostoa.
  Se ei ole digitaalinen allekirjoitus eikä muuta olemassa olevan asentimen
  per-artifact-tarkistuksia.

Verkkotarkistus teki HEAD-pyynnöt 23 Conda- ja 144 wheel-URL:iin sekä nykyisen
Miniforge ARM64 -bootstrapin, GitHub-repositorion ja main-ZIPin osoitteisiin:
**170/170 PASS**. Redirectit seurattiin. Pakettisisältöä ei ladattu eikä
artifact-hasheja laskettu uudelleen verkosta. Lukitusrivien hash-muodot ja
versiovastaavuus tarkistettiin paikallisesti. Lukitusten sisältö säilyi samana
kuin hyväksytyssä tuotantoasennuksessa.

Miniforge säilyttää olemassa olevan `releases/latest`-bootstrap-valinnan;
Conda-perustan tarkkaa versiota ei uutena politiikkana lukittu. Tieteellinen
ympäristö tulee explicit/require-hashes-lukituksista, ei uudesta solver-ajosta.
APT ja `/opt/rpi`:n nykyinen Conda-pakettivalinta säilyvät nykyisellä
versiopolitiikalla. Toistettavuus ei tarkoita koko OS-kuvan bittitarkkaa
uudelleenrakennusta vaihtelevista APT-lähteistä.

Nykyiset asennusskriptit käyttävät niiden omiin hakemistoihin suhteutettuja
resursseja. Staattinen tarkistus tehtiin lähdekopiosta, jossa ei ole `.git`-
hakemistoa: tarvittavat resurssit olivat mukana eikä install/config-lähteissä
ollut `file://`-, Niobium-kotihakemisto- tai T9-riippuvuutta. Tämä tukee sekä
kloonatun että ZIPistä puretun lähdepuun käyttöä. Varsinaista uutta ympäristöä
kummastakaan hankintatavasta ei rakennettu tässä tehtävässä.

## Työnjako ja tallennusmedia

Trixie-malliasennus huolehtii OS:stä, APT-kehityskirjastoista ja Python-
ympäristöistä. Scientific Imagingin nykyinen asennin huolehtii sovelluksista.
Tämän repositorion cam-imgcheck-pilotti ja Scientific Imagingin siitä jatkettu
asennin säilytettiin rinnakkain; niitä ei poistettu, korvattu tai yhdistetty.
Samalle sovellukselle ei oteta kahta omistajuusketjua automaattisesti.

VRecorder Full RPi:n pysyvä ext4-vaatimus viitataan kamerakoneen ohjeissa.
Metadatan viimeinen julkaisuvaihe käyttää kovaa linkkiä, jota exFAT ei tue.
Viittaus on sovelluskohtainen, ei kaikkien dataloggereiden tai sovellusten
yleinen tallennusmedian rajoitus. Uutta exFAT-adapteria ei tehty.

## Rajatut tarkistukset ja julkaisuvalmius

| Tarkistus | Tulos |
|---|---|
| Bash-syntaksi: 30 install-skriptiä sekä envrun ja rpi-share | PASS, 32 tiedostoa |
| Common/RPi APT-listat: nimet, duplikaatit, ei versiolukituksia | PASS, 64 yksilöllistä nimeä |
| Lisättyjen pakettien todelliset APT-ehdokkaat | PASS, 11/11 |
| Lukitusten ja 145-jakelun sopimuksen versiot ja hash-muodot | PASS |
| Kolmen lukitustiedoston toimitustarkisteet | PASS |
| Tuotannon vastaavuus nykyiseen sopimukseen, vain metatietojen luku | PASS, 0 eroa |
| Skriptien olennaiset suhteelliset resurssipolut | PASS |
| HOME/AALTO-järjestys ja `/opt/rpi`-valinnaisuus | PASS, säilytetty |
| Uusien ohjeiden paikalliset dokumenttilinkit | PASS |
| Paketti-, bootstrap-, GitHub- ja ZIP-URLien HEAD-saatavuus | PASS, 170/170 |
| Uusi koko regression / uusi Spyder-GUI-kierros | NOT RUN, aiempi 103 PASS hyödynnetty |
| OS/APT-päivitys tai Python-ympäristön uudelleenasennus | NOT RUN, ei valtuutettu tässä tehtävässä |
| Puhdas erillinen 64 GB testikortti ja kloonattu 128 GB tuotantomalli | NOT TESTED, seuraava laitevaihe |
| Tämän version commit, push ja juuri julkaistun GitHub-ZIPin asennus | NOT RUN, vaatii julkaisuhyväksynnän |

Paikallinen kokonaisuus on valmisteltu commit/push-hyväksyntää varten;
uudet lukitukset ja muut ennestään untracked-tiedostot on sisällytettävä samaan
julkaisuun. Nykyisen GitHub-osoitteen saatavuus ei osoita, että tämä vielä
julkaisematon työpuu olisi jo ladattavissa sieltä.

Käynnistysprofiilien nykyiset käyttäjäoletukset ja rpi-share HOME/AALTO -mallien
host/user/share-asetukset tunnistettiin profiilikohtaisiksi. Ne eivät sisällä
tallennettuja salasanoja, ja ne on tarkistettava kohdeasennukselle ennen
mallikuvan kloonausta. Niitä ei poistettu tai muutettu uudeksi käyttäjälogiikaksi.
Rajattu inventaario kattoi 80 tiedostoa / noin 0,50 MB. Yli 5 MiB tiedostoja,
avainten/tunnisteiden nimisiä tiedostoja tai tarkistettujen yleisten
private-key-/GitHub-/AWS-token-muotojen osumia ei löytynyt. Tämä ei ole
kaikkien mahdollisten salaisuuksien kattava auditointi.
Uusia konekohtaisia asetuksia, paketteja, välimuisteja, videoita tai testiympäristöjä
ei lisätty repositorioon. Vanhat kehitysraportit säilyivät.

Niobiumin työaineisto oli tarkistetussa RAM-/tmp-hakemistossa. Pi:lle ei tehty
väliaikaista asennusta, pakettivälimuistia tai testitallennuksia. Olemassa olevien
skriptien olennaiseen asennukseen kuuluvaa cache-menetelmää ei muutettu:
lab314:n cache on uuden prefiksin vieressä ja poistuu EXIT-trapissa;
epäonnistunut prefiksi säilytetään nykyiseen tapaan.

**Poikkeamat sovituista ratkaisuista: EI OLE.**
Toteuttamattomia arkkitehtuurimuutoksia ei otettu käyttöön. Sovellusasentimien
mahdollista myöhempää yhdistämistä ei toteutettu eikä uuden testijärjestelmän
rakentamista aloitettu.
