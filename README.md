# vivi

Bu proje Vavoo kanal listesini cekip `output/*.m3u8` dosyalarina ham Vavoo
catalog URL'lerini yazar.

Playlist icine nihai HLS adresi yazilmaz. Cunku HLS adresleri degisebilir.
Bu nedenle output dosyalarinda sadece su tip ham Vavoo linkleri tutulur:

```text
https://vavoo.to/vavoo-iptv/play/...
```

Sen daha sonra GitHub raw playlist URL'sini su proxy ile acarsin:

```text
https://prxy.canparlak.com/proxy/manifest.m3u8?url=<playlist_raw_url>
```

## Kullanim

```bash
python3 scraper.py
```

## Not

`live2/play3/...` linkleri artik output'a yazilmaz. Playlist'lere yalnizca Vavoo
API'den gelen ham `vavoo-iptv/play/...` kanallari eklenir.
