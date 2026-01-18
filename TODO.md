# TODO

## En cours

- Samedi

  - Factoriser les fonctions en les prefixant avec _compile_
  - voir s'il faut renommer get_compilation_parametres (si ça ne concerne pas que la compilation) : ex: get_parametres_locaux
  - pour liste-fichier, ajouter un parametre pour lister les fichiers rejetés (qui retourne la raison du rejet)

- Paramètres

  - Prévoir un fichier pyUPSTIlatex-custom.json
  - Prévoir aussi une classe UPSTILatexDocumentCustom

- Compiler

  - Créer les fonctions pour ajouter ou supprimer des métadonnées dans un document (en v1 et en v2)

- LaTeX

  - Penser à une difficulté (1,2,3) et à la possibilité de préciser si la question doit savoir être traitée !

## Roadmap

1. Finir le script de compilation
2. Scripts pour modifier les fichier tex : ajouter/modifier balise/meta, supprimer, modifier zone, etc...
3. Script de migration v1 <-> v2
4. Poly de td et de colles

## À faire plus tard

- [ ] Faire un script pour afficher les valeurs possibles des différentes paramètres

## Fonctionnalités

- [ ] Faire un script plus propre de conception de poly de TD : ajout d'une meta : is_in_poly = True/False, compilation dans un seul fichier tex, création de la table des matieres, etc... ou bien on conserve l'étape de transition par le fichier xml... L'idée serait de faire un seul poly en compilant directement les contenus des fichiers tex, sans rajouter de pages blanches, du coup...

### Migration -> UPSTIv2

- renommer les dossiers en virant les majuscules
- supprimer @parametres.upsti.ini et le remplacer si nécessaire par le YAML

## Release

- Faire une copie vide du fichier .env pour la distrib
