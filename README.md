Viberen készíts egy csatornát.

A csatornán lépj a beállítások --> Developer Tools menüpontba és 
                                    másold ki az ott található tokent a json.config file-ba. 

Manuális telefonszám lekérdezés Powershellben:
python viber_lekerdezes.py --phone +36301234567

Több telefonszám lekérdezése Powershellben:
python viber_lekerdezes.py --list phones.txt

Várható eredmény:

Flask started on http://127.0.0.1:5000
Cloudflare URL: https://example.trycloudflare.com
Webhook configured:
https://example.trycloudflare.com/webhook
Contact message accepted for +36301234567
Server is running. Press Ctrl+C to stop.

A csatornán fognak megjeleni a számok "ITT Nyisd meg a profilt!" névvel.

Az egyes nevekre kattintva végigtudod nézni, hogy van regisztráció:
1) Ha a név és a profilkép nem változik, akkor nincs profilja.
2) Ha a név és a profilkép VÁLTOZIK, akkor van regisztráció.
