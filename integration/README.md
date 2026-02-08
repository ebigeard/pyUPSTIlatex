# Intégration

Ce dossier contient des fichiers et des instructions pour intégrer pyUPSTIlatex à l'OS (principalement Windows).

## Commandes Windows

Les scripts présents sont des fichiers `.cmd` destinés à être placés dans le menu Windows « Envoyer vers ». Vous pouvez aussi utiliser l'icône `icone/pyUPSTIlatex.ico` pour illustrer des raccourcis.

Pour ouvrir le dossier « Envoyer vers », lancez la commande suivante depuis la boîte Exécuter (Win+R) :

```powershell
shell:SendTo
```

Pour ajouter une commande au menu, copiez simplement le fichier `.cmd` dans ce dossier.

## YAML

Le fichier `@parametres.pyUPSTIlatex.yaml` peut être copié dans le même dossier que un fichier `.tex` qui utilise `UPSTI_Document` ou `upsti-latex`. Cela permet :

- de surcharger les métadonnées du document, et
- de préciser les paramètres de compilation pour ce fichier uniquement.

Exemples de copie :

```cmd
rem Exemple Windows (cmd)
copy @parametres.pyUPSTIlatex.yaml C:\chemin\vers\mon\document\
```

```bash
# Exemple POSIX (bash)
cp @parametres.pyUPSTIlatex.yaml /chemin/vers/mon/document/
```

Placez le fichier YAML au même niveau que votre `.tex` pour que pyUPSTIlatex le découvre automatiquement.
