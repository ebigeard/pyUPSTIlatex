# pyUPSTIlatex

<!-- markdownlint-disable MD033 -->
<div align="center">
  <img src="integration/icones_et_logos/pyUPSTIlatex.png" alt="Logo pyUPSTIlatex" width="200"/>
  
  ![Version](https://img.shields.io/badge/version-2.0.0-green)
  ![Status](https://img.shields.io/badge/status-beta-orange)
  ![License](https://img.shields.io/badge/license-GPL--3.0-blue)
  ![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
  ![LaTeX](https://img.shields.io/badge/LaTeX-%23008080?logo=latex&logoColor=white)
</div>
<!-- markdownlint-enable MD033 -->

## Description

**pyUPSTIlatex** est un outil en ligne de commande complet pour gérer, compiler et automatiser la production de documents LaTeX initialement conçu pour les Sciences Industrielles de l'Ingénieur (S2I) en Classes Préparatoires aux Grandes Écoles (CPGE).

Il peut néanmoins être adapté à n'importe quel niveau ou discipline, moyennant quelques étapes de personnalisation.

Compatible avec les packages LaTeX `upsti-latex` (et `UPSTI_Document`), pyUPSTIlatex simplifie la gestion de documents pédagogiques (cours, TD, TP, colles) en automatisant la compilation, le versionnage, l'upload FTP et la génération de polys.

> « En tant que professeur de S2I en CPGE PT, je dois gérer une grande quantité de documents pédagogiques (plus de 600 cours, TD, TP, colles, QCM, DS, DM, etc.), avec de nombreux contenus scientifiques (équations, schémas, graphiques, etc.). Ce volume de documents à gérer rend la tâche ardue. Uniformiser et maintenir ces documents nécessite un peu d'organisation, et rend incontournables un certain nombre de micro tâches rébarbatives qu'il serait intéressant d'automatiser. »

<!-- markdownlint-disable MD033 -->
<div align="center">
<img width="500" height="345" alt="synopsis" src="https://github.com/user-attachments/assets/32915143-f25f-46ca-b7d8-9fe780417567" />
</div>
<!-- markdownlint-enable MD033 -->

En savoir plus en consultant le wiki : [Concepts et structure du projet](https://github.com/ebigeard/pyUPSTIlatex/wiki/Concepts-et-structure-du-projet)

## Fonctionnalités principales

- **Compilation intelligente** avec gestion des versions élève/prof/documents à compléter, etc.
- **Versions accessibles** : génération automatique de documents accessibles : dys, déficients visuels...
- **Génération de polys** de TD ou de colle
- **Upload FTP** automatisé avec webhook optionnel pour synchronisation sur un site internet
- **Traitement par lot** de documents (liste des documents compatibles, compilation par lots, etc.)
- **Intégration à l'OS** : affichage de la version, des métadonnées, etc. depuis le menu contextuel de l'explorateur
- **Personnalisation** : possibilité de surcharger la configuration TOML, les templates et différentes classes

### En cours de développement

- **Création des en-têtes et pieds de page LaTeX** à partir de templates générés par pyUPSTIlatex

## Releases

La version actuelle est **v2.0.0** (beta 1).

Pour télécharger la dernière version stable ou consulter l'historique complet des versions : **[Releases GitHub](https://github.com/ebigeard/pyUPSTIlatex/releases)**

Consulter le [CHANGELOG.md](CHANGELOG.md) pour le détail des modifications entre chaque version.

## Installation

### Prérequis

- **Python** 3.9 ou supérieur
- **LaTeX** (TeX Live, MiKTeX) avec pdflatex
- Packages LaTeX : `upsti-latex` (en cours de développement) ou `UPSTI_Document` ([Télécharger](https://s2i.pinault-bigeard.com/ressources/latex/69-packages-latex-pour-les-sciences-de-l-ingenieur-upsti))

### Installation standard

```bash
# Cloner le dépôt
git clone https://github.com/ebigeard/pyUPSTIlatex.git
cd pyUPSTIlatex

# Installer le package avec toutes ses dépendances (automatique via pyproject.toml)
pip install -e .
```

> **Note** : Cette commande installe automatiquement toutes les dépendances requises (PyYAML, click, python-dotenv, regex, tomli pour Python < 3.11)

## Démarrage rapide

### Configuration initiale

Consulter le wiki [Configuration et personnalisation](https://github.com/ebigeard/pyUPSTIlatex/wiki/Configuration-et-personnalisation) pour plus de détails.

1. **Créer les fichiers de configuration personnalisés :**

```bash
cp custom/config.toml.template  custom/config.toml
cp custom/.env.template custom/.env
```

<!-- markdownlint-disable MD029 -->

2. **Configuration TOML** (`custom/config.toml`) :

Surcharger les paramètres nécessaires (en vous inspirant de `pyupstilatex/config/custom/config.default.toml`)

```toml
[meta.default]
auteur = "Votre Nom"
classe = "MPSI"
matiere = "S2I"

[compilation.defaut]
upload = false  # Désactiver l'upload par défaut

[ftp]
mode_local = true
mode_local_dossier = "C:/tmp/documents"
```

3. **Secrets** (`custom/.env`) :

Surcharger les paramètres nécessaires (en vous inspirant de `custom/.env.template`)

```bash
FTP_HOST=ftp.example.com
FTP_USER=username
FTP_PASSWORD=password
```

<!-- markdownlint-enable MD029 -->

### Utilisation basique

```bash
# Afficher la version d'un document
pyupstilatex version chemin/vers/document.tex

# Afficher les informations complètes (métadonnées)
pyupstilatex infos chemin/vers/document.tex

# Lister les fichiers LaTeX compatibles dans un dossier
pyupstilatex liste-fichiers chemin/vers/dossier

# Compiler un document
pyupstilatex compile chemin/vers/document.tex

# Compiler tous les documents d'un dossier
pyupstilatex compile chemin/vers/dossier

# Créer un poly de TD (en 2 temps)
pyupstilatex poly chemin/vers/dossier
pyupstilatex poly chemin/vers/dossier/_poly/poly.yaml

# Mettre à jour automatiquement le fichier pyUPSTIlatex.json
pyupstilatex update-config
```

## Configuration

pyUPSTIlatex utilise une **configuration en cascade** :

1. **`config.default.toml`** : Configuration par défaut (versionnée)
2. **`custom/config.toml`** : Surcharges locales (non versionnée)
3. **`custom/.env`** : Secrets uniquement (FTP, API keys)

### Sections de configuration

- **`[meta.default]`** : Métadonnées par défaut des documents
- **`[compilation.defaut]`** : Paramètres de compilation
- **`[os.format]`** : Format des noms de fichiers
- **`[os.suffixe]`** : Suffixes (prof, élève, etc.)
- **`[os.dossier]`** : Arborescence des dossiers
- **`[ftp]`** : Configuration FTP
- **`[poly]`** : Paramètres des polys

Consultez le wiki [Configuration et personnalisation](https://github.com/ebigeard/pyUPSTIlatex/wiki/Configuration-et-personnalisation) pour le guide complet.

## Documentation

La **documentation complète** est disponible sur le [**Wiki GitHub**](https://github.com/ebigeard/pyUPSTIlatex/wiki) :

1. [Concepts et structure du projet](https://github.com/ebigeard/pyUPSTIlatex/wiki/Concepts-et-structure-du-projet)
2. [Guide d'installation détaillé](https://github.com/ebigeard/pyUPSTIlatex/wiki/Guide-d'installation-détaillé)
3. [Configuration et personnalisation](https://github.com/ebigeard/pyUPSTIlatex/wiki/Configuration-et-personnalisation)
4. [Préparation de l'environnement pour utiliser pyUPSTIlatex](https://github.com/ebigeard/pyUPSTIlatex/wiki/Préparation-de-l'environnement)
5. [Commandes CLI](https://github.com/ebigeard/pyUPSTIlatex/wiki/Commandes-CLI)

## Exemples d'utilisation

### Compilation avec options

```bash
# Compilation en mode "deep" (régénération complète)
pyupstilatex compile document.tex --mode deep

# Simulation (dry-run)
pyupstilatex compile document.tex --dry-run
```

### Traitement par lot

```bash
# Compiler tous les documents d'un dossier
pyupstilatex compile chemin/vers/dossier
```

### Génération de poly

```bash
# Créer le fichier YAML de configuration
pyupstilatex poly chemin/vers/TD

# Le poly.yaml est généré, le modifier si nécessaire, puis compiler
pyupstilatex poly chemin/vers/TD/_poly/poly.yaml
```

### Utilisation programmatique (API Python)

```python
from pyupstilatex import UPSTILatexDocument
from pyupstilatex.config import load_config

# Charger la configuration
cfg = load_config()

# Ouvrir un document
doc, errors = UPSTILatexDocument.from_path("document.tex")

# Extraire les métadonnées
metadata, _ = doc.get_metadata()
titre = doc.get_metadata_value("titre")
classe = doc.get_metadata_value("classe")

# Compiler le document
result, messages = doc.compile(mode="normal")

# Modifier une métadonnée
doc.set_metadata("version", "2.1")
doc.save()
```

## Contribution

Les contributions sont les bienvenues ! Consultez le guide [CONTRIBUTING.md](CONTRIBUTING.md) pour plus de détails.

## License

Ce projet est sous licence **GNU General Public License v3.0**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## Auteur

Emmanuel Bigeard - mail : [s2i@bigeard.me](s2i@bigeard.me) - site internet : [https://s2i.bigeard.me](https://s2i.bigeard.me)

## Remerciements

- [Raphaël Allais](https://allais.eu/), dont les packages LaTeX pour la SI m'ont servi de base pour la création d'`UPSTI_Document`
- Tous les collègues qui utilisent `UPSTI_Document` pour concevoir leurs documents pédagogiques (et qui ont eu la patience de lire mes documentations vaguement rédigées)
- Tous les collègues qui partagent leur travail sur des sites perso
- L'[UPSTI](https://upsti.fr) (Union des Professeurs de Sciences et Techniques Industrielles) et la communauté des enseignants de CPGE S2I

## Changelog

Voir [CHANGELOG.md](CHANGELOG.md) pour l'historique des versions.

## Support

- **Bugs report** : [GitHub Issues](https://github.com/ebigeard/pyUPSTIlatex/issues)
- **Discussions** : [GitHub Discussions](https://github.com/ebigeard/pyUPSTIlatex/discussions)
- **Documentation** : [Wiki](https://github.com/ebigeard/pyUPSTIlatex/wiki)
