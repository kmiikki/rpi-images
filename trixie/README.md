# Raspberry Pi OS Trixie — laboratorion malliasennus

`base/` on Raspberry Pi OS **Trixie Full, 64-bit** -pohjainen yleiskäyttöinen
laboratorioasennus kamerakoneisiin, dataloggereihin ja muihin tutkimuslaitteisiin.
Tuotantokortti on vähintään **128 GB**. Puhdas asennus testataan ensin erillisellä
Pi:llä ja 64 GB:n testikortilla; testi ei muuta tuotantokorttivaatimusta.

Nykyinen hyväksytty ympäristöjako:

| Polku | Tarkoitus |
|---|---|
| `/opt/conda` | Conda/Miniforge-perusta |
| `/opt/lab314` | lukittu Scientific Python: Python 3.14.10, OpenCV 5.0.0, Shapely 2.2.0 / GEOS 3.14.1, 145 jakelua |
| `/opt/rpi` | valinnainen laitteistoympäristö, Trixien Python 3.13:n APT-kamerakirjastot ja laiterajapinnat |
| `/opt/sci/bin` | yleiset Scientific Imaging -komennot |
| `/opt/sci/bin-rpi` | Pi-kohtaiset Scientific Imaging -komennot |
| `/opt/sci/lib` | sovellusten tukitiedostot |

## HOME ja AALTO

Käytä vain toista profiilia. Komennot suoritetaan kloonatusta tai puretusta
ZIP-paketista samoin; asennusskriptit eivät tarvitse Git-metatietoja.

```sh
cd rpi-images/trixie/base/install
sudo bash run_rpi_home.sh
# vaihtoehtoisesti:
sudo bash run_rpi_aalto.sh
```

Nykyinen käynnistysjärjestys ja `/opt/rpi`-ympäristön valinnaisuus säilyvät.
Kamerakoneessa ota `/opt/rpi` käyttöön perusasennuksen jälkeen
[base-ohjeen](base/README.md#kamerakoneen-laitteistoympäristö) mukaan.
Valinnainen aiempi `--with-cam-imgcheck POLKU` -pilottivalinta säilyy myös.

Trixie-malliasennus vastaa käyttöjärjestelmästä, APT-riippuvuuksista ja Python-
ympäristöistä. Scientific Imagingin oma asennin asentaa kuvantamissovellukset;
sovelluswrappereita tai uutta käynnistysjärjestelmää ei lisätä.
Meson/Ninja, libcamera-kehityskirjasto sekä todetut DRM/EGL-preview'n kehitys-
riippuvuudet ovat Pi:n APT-luettelossa, ilman tarpeettomia versiolukituksia.

VRecorder Fullin ensimmäisen RPi-version pysyvän videotallennuskohteen tulee
olla ext4: metatiedon viimeinen julkaisuvaihe käyttää kovaa linkkiä.
Tarkka sovelluskohtainen perustelu on Scientific Imaging -repon tiedostossa
`docs/architecture/VRECORDER_STORAGE_FILESYSTEM_RPI_LINUX.md`. Vaatimus ei koske kaikkia dataloggereita tai
muita laboratorio-ohjelmia.

Katso [asennusohje](base/README.md),
[lab314:n hyväksytty tuotantotila](base/docs/lab314/production-final-result-20261114.md)
ja [malliasennuksen viimeistelyraportti](base/docs/trixie-model-finalization-20261114.md).

`rpi-share` ja vanhat `/opt/lab`-työkalut säilyvät nykyisillä poluillaan;
niitä ei siirretä tai poisteta Scientific Imaging -polkujen käyttöönotossa.
[Rpi-share-ohje](base/docs/rpi-share.md).
