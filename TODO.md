# TODO

## En cours

- Paramètres

  - Prévoir un fichier pyUPSTIlatex-custom.json

- Compiler
  - Récupérer les métadonnées et les paramètres de compilation
  - Renommer le fichier si nécessaire
  - Check de doublons id_document sur le site si nécessaire (rajouter url de check dans le .env)
  - Compilation (s) des fichiers tex
  - Créer le fichier sources.zip
  - Copier dans le fichier cible (si param)
  - Générer le fichier .meta.json (ou .meta.yaml) (mettre une variable : changement_parametres_obligatoires=bool pour voir si on detecte les doublonsou pas)
  - Uploader sur le FTP
  - Envoyer une requete d'actualisation sur le site (rajouter url dans le .env)
- Penser à une difficulté (1,2,3) et à la possibilité de préciser si la question doit savoir être traitée !

## Roadmap

1. Script pour corriger les doublons d'id_document

## CLI

- liste : liste les documents contenus dans un dossier qui possèdent tels ou tels attributs (options de package, type, etc...)
- change-parametre : change la valeur d'un paramètre ou d'une métadonnée
- compil : compiler un fichier tex
- quick-compil : compilation rapide
- migrate : migration vers UPSTI_Document v3
- create-poly-td : création d'un poly de TD
- create-poly-colles : création d'un ou des polys de colle
- merge-pdf : fusionner plusieurs pdf (avec plusieurs pages ou non)

## À faire plus tard

- [ ] Faire un script pour afficher les valeurs possibles des différentes paramètres
- [ ] Ajouter un pyUPSTIlatex_custom.json pour rajouter des variantes par exemple

## Fonctionnalités

- [ ] Faire un script plus propre de conception de poly de TD : ajout d'une meta : is_in_poly = True/False, compilation dans un seul fichier tex, création de la table des matieres, etc... ou bien on conserve l'étape de transition par le fichier xml... L'idée serait de faire un seul poly en compilant directement les contenus des fichiers tex, sans rajouter de pages blanches, du coup...

### Migration -> UPSTIv2

- renommer les dossiers en virant les majuscules
- supprimer @parametres.upsti.ini et le remplacer si nécessaire par le YAML

## Release

- Faire une copie vide du fichier .env pour la distrib
