# TODO

- Parse des metadonnees possible aussi avec \begin{comment}
- Il faut finir pyUPSTIlatex avant de faire le site (sauf tout ce qui concerne la compilation v2)
- Faire un .env exemple
- Changer UPSTI_Document_v2 en upsti-latex

## En cours

- Paramètres
  - Prévoir un fichier pyUPSTIlatex-custom.json
  - Prévoir aussi une classe UPSTILatexDocumentCustom

## upsti-latex

### A terminer

- UPSTILatexDocument
  - TODO : `\_generate_latex_template`
  - TODO : `\_generate_UPSTI_Document_v1_tex_file`
  - TODO : `\_create_accessible_version` : voir s'il faut passer par le handler pour créer les versions accessibles
- Script d'adaptation à pyUPSTIlatex
  - mettre à jour les id_unique (ajout si manquant, détection de doublons)
  - renommer les dossiers en virant les majuscules
  - supprimer @parametres.upsti.ini et le remplacer si nécessaire par le YAML (faire un script par dossier, avec la définition des paramètres dans la ligne de commande)
  - changer Src en src (le nom du dossier et dans les fichiers tex...), pareil pour les dossiers spécifiés dans le config, et pour les suffixes de fichiers
- Script de migration v1 -> v2

### En projet

- Combiner tous les polys de TD en un seul, avec pagination qui va bien.

## LaTeX

### création des input tex

- utiliser jinja 2 ?
- Faire un dossier de templates par défaut avec possibilité d'override (avec les images aussi, et les packages) et possibilité de spécifi la variante dans le fichier YAML (d'abord on regarde si le nom du template spécifié est un sous_dossier de templates\custom_EB, sinon, on regarde dans template\defaut). On peut spécifier le nom du template dans le .env ou dans le .YAML, et la variante du template (colle1, colle2, cours1, etc...) dans le fichier YAML uniqument.

### Template upsti-latex

- Penser à une difficulté (1,2,3) et à la possibilité de préciser si la question doit savoir être traitée !

### Déploiement

## Release

- Faire une copie vide du fichier .env pour la distrib
- Peaufiner le fichier README.md
