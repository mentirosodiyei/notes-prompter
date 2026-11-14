NOTES PROMPTER

Agent llegeix les notes del PowerPoint local i les envia per la xarxa.
Escoltar rep les notes, aplica preconfiguracions i mostra el prompter a la pantalla triada.
Només Escoltar té Panell d’administració. Connecta Companion a aquest receptor, port 8765.

Vincula una preconfiguració a cada PowerPoint i desa les regles de les diapositives.
La detecció automàtica fa servir el nom del fitxer i el número de diapositiva.
Fes servir noms diferents per a presentacions diferents.

Idioma automàtic segons el sistema: català, castellà o anglès per a la resta.
Les notes i els noms introduïts per l’usuari no es tradueixen.

Tanca l’aplicació amb Aplicació > Sortir abans d’actualitzar-la. La X la manté en segon pla.
Els ajustos es conserven a %LOCALAPPDATA%\NotesPrompter\settings.json.
Cal PowerPoint per a l’Agent local i Chrome/Edge per a la sortida d’Escoltar.

Fes servir una xarxa de confiança: TCP 8765 i UDP 8766 no tenen autenticació ni xifratge.
No exposis el servei a Internet. No es modifiquen regles del tallafoc.
