# TODO

## En cours

- Faire une fonction pour créer un fichier yaml partout...
- Faite un cli update_config pour télécharger le contenu du json depuis le site
- Mettre les fonctions de utils.py dans file_system
- Paramètres
  - Prévoir un fichier pyUPSTIlatex-custom.json
  - Prévoir aussi une classe UPSTILatexDocumentCustom
  - Prévoir comment overrider les fichiers accessibilité

## Migration

### pyUPSTIlatex

- Script d'adaptation à pyUPSTIlatex
  - mettre à jour les id_unique (ajout si manquant, détection de doublons)
  - renommer les dossiers en virant les majuscules
  - supprimer @parametres.upsti.ini et le remplacer si nécessaire par le YAML (faire un script par dossier, avec la définition des paramètres dans la ligne de commande)
  - changer Src en src (le nom du dossier et dans les fichiers tex...), pareil pour les dossiers spécifiés dans le config, et pour les suffixes de fichiers
- Quand on aura mis en place upsti-latex
  - faire 2 fonctions convert UPSTI_Document -> upsti-latex et upsti-latex -> UPSTI_Document
  - Coder `\_generate_latex_template`
  - Coder `\_generate_UPSTI_Document_tex_file`
  - Combiner tous les polys de TD en un seul, avec pagination qui va bien.

## LaTeX

### création des input tex

- Faire un dossier de templates par défaut avec possibilité d'override (avec les images aussi, et les packages) et possibilité de spécifi la variante dans le fichier YAML (d'abord on regarde si le nom du template spécifié est un sous_dossier de templates\custom_EB, sinon, on regarde dans template\defaut). On peut spécifier le nom du template dans le .env ou dans le .YAML, et la variante du template (colle1, colle2, cours1, etc...) dans le fichier YAML uniqument.

### Template upsti-latex

- Penser à une difficulté (1,2,3) et à la possibilité de préciser si la question doit savoir être traitée !

### Déploiement

## Release

- Peaufiner le fichier README.md
- Faire une copie vide du fichier .env pour la distrib
- Faire un .env exemple
- Créer l'icône pyUPSTIlatex.ico
