# TODO

## Roadmap

3. Faire la vérification du parser v1
4. Nettoyer et simplifier logger.py (virer fonctions inutiles, déporter checkfile, vérifier \_annoted_text)
5. Comprendre exceptions.py
6. Vérifier si le sorage est utile, sachant que sur le site django, on ne se servira que de get_metadonnees
7. Faire un nettoyage global pour virer tout ce qui ne sert à rien
8. Etendre CLI infos aux dossiers (ecrire ce qui permet de balayer les dossiers et de choisir les fichiers corrects)

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
