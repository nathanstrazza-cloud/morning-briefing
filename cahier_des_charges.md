# Morning Briefing — Cahier des charges V1

## 1. Objectif du projet

Créer un site web personnel de veille d'actualité automatisée.

Le site doit chaque matin sélectionner, vérifier, synthétiser et présenter les informations les plus importantes pour l'utilisateur.

Le projet est actuellement destiné à un seul utilisateur.

### Priorité absolue

**La fiabilité et la véracité des informations passent avant la quantité, la vitesse et la personnalisation.**

Il vaut mieux afficher 5 informations réellement importantes et correctement vérifiées que 20 informations secondaires ou incertaines.

La personnalisation avancée sera développée ultérieurement. La V1 doit principalement appliquer les préférences définies ci-dessous.

---

# 2. Fonctionnement général

Du lundi au vendredi, le système doit générer automatiquement un nouveau briefing chaque matin.

Horaire cible :

**06h30 — heure française (Europe/Paris)**

Le site doit afficher :

- la date du briefing ;
- l'heure de la dernière mise à jour ;
- le briefing correspondant au dernier traitement réussi.

Le site n'a pas besoin d'envoyer une notification.

L'utilisateur consulte simplement le site lorsqu'il le souhaite.

---

# 3. Particularité du lundi

Le briefing du lundi doit être plus important et plus complet.

Il doit couvrir :

- le samedi ;
- le dimanche ;
- éventuellement les informations importantes apparues très tôt le lundi matin.

Le système ne doit donc pas se limiter aux dernières 24 heures le lundi.

Il doit effectuer une recherche suffisamment large pour reconstituer les événements importants du week-end.

Les autres jours, la recherche porte principalement sur la période depuis le briefing précédent.

---

# 4. Structure du briefing

Le briefing doit être organisé dans cet ordre.

## A. Actualité — PRIORITÉ MAXIMALE

Cette section est la plus importante du site.

Elle couvre :

### France
- politique lorsqu'elle a une importance nationale ;
- économie ;
- catastrophes ;
- événements majeurs ;
- décisions importantes ;
- événements sociaux lorsque leur importance le justifie.

### Monde
- géopolitique ;
- guerres et conflits ;
- tensions internationales ;
- diplomatie ;
- catastrophes naturelles ou humaines majeures ;
- événements économiques importants ;
- décisions internationales majeures.

### Règle

Ne pas chercher à remplir artificiellement cette section.

Une actualité doit être retenue lorsqu'elle est suffisamment importante pour que l'utilisateur puisse raisonnablement se dire :

> « Il était utile que je sache cela ce matin. »

---

# 5. Marchés financiers

Suivre principalement :

- CAC 40 ;
- S&P 500 ;
- Nasdaq ;
- principaux indices européens ;
- autres grands marchés lorsque leur évolution est particulièrement importante ;
- pétrole ;
- or ;
- éventuellement autres actifs lorsqu'un événement majeur le justifie.

Ne pas simplement donner les variations.

Exemple :

> CAC 40 : -2,1 %

doit être accompagné d'une explication lorsque le mouvement est inhabituel.

Le système doit chercher :

**Pourquoi le marché a-t-il fortement bougé ?**

Si aucune cause fiable n'est identifiée, ne pas inventer d'explication.

Les petites variations quotidiennes sans intérêt doivent être ignorées.

---

# 6. Sports

## Football

Suivre :

- Ligue 1 ;
- Ligue des champions ;
- Europa League.

Retenir principalement :

- résultats importants ;
- classements lorsqu'ils deviennent significatifs ;
- performances remarquables ;
- blessures importantes ;
- transferts ou annonces majeures ;
- événements exceptionnels.

Ne pas faire un compte-rendu exhaustif de tous les matchs.

---

## Basketball

Suivre :

- NBA ;
- San Antonio Spurs en priorité ;
- Euroligue.

Pour les Spurs, le niveau de détail peut être supérieur aux autres équipes.

Retenir notamment :

- résultats ;
- performances individuelles remarquables ;
- blessures ;
- actualités importantes ;
- transferts ;
- événements ayant un impact sur la saison.

---

## Natation

Ne suivre régulièrement que lorsqu'il existe :

- Championnat d'Europe ;
- Championnat du monde ;
- autre compétition internationale majeure pertinente.

Faire alors un bref résumé :

- résultats français ;
- grandes performances ;
- records ;
- surprises ;
- événements marquants.

---

## Autres sports

Suivre uniquement lorsqu'une équipe de France joue :

- tennis ;
- handball ;
- volley ;
- cyclisme ;
- rugby.

Dans ce cas :

- annoncer le match / événement ;
- donner le résultat s'il a déjà eu lieu ;
- signaler les événements importants.

Ne pas produire de veille quotidienne sur ces sports lorsqu'il ne se passe rien d'important concernant la France.

---

# 7. Sciences / technologie / corps humain

Cette section fonctionne selon deux modes.

## Mode 1 — découverte majeure

Si une découverte ou une avancée réellement importante est survenue récemment :

- science ;
- médecine ;
- corps humain ;
- climat ;
- énergie ;
- technologie ;
- intelligence artificielle ;
- informatique ;
- espace ;

alors elle doit être présentée comme sujet principal.

Exemple :

> Un nouveau modèle d'IA atteint une capacité auparavant considérée comme difficile.

ou

> Une découverte importante permet de mieux comprendre une maladie.

La nouveauté doit être vérifiée et son importance ne doit pas être exagérée.

---

## Mode 2 — sujet approfondi

S'il n'y a pas de découverte majeure, sélectionner un sujet pédagogique intéressant.

Exemples :

- intelligence artificielle ;
- émissions de CO2 ;
- champs magnétiques ;
- formation des cyclones ;
- glucides : fonctionnement, avantages et limites ;
- sommeil ;
- cerveau ;
- muscles ;
- énergie ;
- climat ;
- nouvelles technologies ;
- etc.

Le sujet doit correspondre à environ **10 minutes de lecture**.

Il doit être suffisamment approfondi pour permettre à l'utilisateur de comprendre réellement le sujet.

Structure recommandée :

1. Introduction
2. Pourquoi le sujet est important
3. Explication du phénomène
4. Fonctionnement / mécanismes
5. Données et résultats scientifiques
6. Ce que les scientifiques savent
7. Ce qui reste incertain
8. Limites et controverses éventuelles
9. Conclusion
10. Sources

Le ton doit être celui d'une **bonne revue scientifique de vulgarisation** :

- précis ;
- pédagogique ;
- compréhensible ;
- sans sensationnalisme.

Ne pas simplifier au point de déformer les connaissances scientifiques.

---

# 8. Météo

Afficher une météo très rapide pour la zone :

**Antibes — Cannes — Valbonne — Grasse**

Le but n'est pas de faire un bulletin météo détaillé.

Afficher notamment :

- température ;
- évolution de la température dans la journée ;
- pluie / risque de pluie ;
- vent si significatif ;
- événements météorologiques importants.

L'utilisateur doit pouvoir comprendre la météo de la journée en quelques secondes.

---

# 9. Citation du jour

Afficher une citation :

- intrigante ;
- intéressante ;
- motivante ;
- philosophique ou intellectuelle.

Afficher systématiquement :

**Citation**

**Auteur**

La priorité est l'authenticité.

Éviter les citations célèbres dont l'attribution est douteuse.

Si l'origine d'une citation ne peut pas être suffisamment vérifiée, ne pas l'utiliser.

---

# 10. Sources

La fiabilité des sources est une priorité fondamentale.

Sources initialement souhaitées :

- Le Monde ;
- L'Équipe ;
- The New York Times ;
- Épsilon.

Mais le système ne doit PAS être limité à ces sources.

Il doit privilégier les sources adaptées au sujet.

Exemples :

### Actualité
- agences de presse ;
- médias reconnus ;
- sources officielles.

### Sciences
- publications scientifiques ;
- universités ;
- organismes scientifiques ;
- revues reconnues.

### Sports
- fédérations ;
- compétitions officielles ;
- clubs ;
- médias sportifs reconnus.

### Économie
- banques centrales ;
- institutions économiques ;
- entreprises concernées ;
- médias économiques reconnus.

### Géopolitique
- gouvernements ;
- organisations internationales ;
- agences de presse ;
- médias reconnus.

---

# 11. Vérification des informations

Le système doit distinguer :

### Fait confirmé
Plusieurs sources fiables concordent ou une source primaire très fiable confirme l'information.

### Information rapportée
Une source fiable rapporte une information qui n'est pas encore suffisamment confirmée.

Dans ce cas utiliser une formulation du type :

> « Selon [source], ... »

### Information incertaine
Ne pas présenter l'information comme un fait.

### Rumeur
Ne pas publier dans la V1 sauf nécessité exceptionnelle, et uniquement en indiquant clairement son statut.

---

# 12. Déduplication

Plusieurs médias peuvent parler du même événement.

Le système doit détecter les doublons.

Exemple :

10 articles parlent tous de la même décision politique.

Cela doit devenir :

**1 événement**

avec plusieurs sources associées.

Ne pas afficher 10 fois la même information.

---

# 13. Importance des informations

Chaque information peut recevoir un score interne d'importance.

Par exemple :

**9–10 : majeur**
- guerre ;
- catastrophe importante ;
- décision politique majeure ;
- événement économique mondial ;
- découverte scientifique majeure.

**7–8 : important**
- événement national ou international notable ;
- résultat sportif important ;
- mouvement de marché significatif.

**5–6 : intéressant**
- événement secondaire mais utile.

**<5 : généralement ignoré**

Ces seuils peuvent être ajustés ultérieurement.

Le score ne doit pas nécessairement être visible sur le site dans la V1.

---

# 14. Style rédactionnel

Le briefing doit être :

- clair ;
- concis pour l'actualité ;
- approfondi pour le sujet scientifique ;
- factuel ;
- sans sensationnalisme ;
- sans opinion politique de l'IA ;
- sans exagération ;
- en français.

Chaque actualité doit idéalement répondre rapidement à :

**Quoi ?  
Où ?  
Quand ?  
Pourquoi est-ce important ?**

Pour les événements complexes :

**Quelles conséquences possibles ?**

Les conséquences doivent être distinguées des faits.

Ne pas présenter une hypothèse comme une certitude.

---

# 15. Interface du site

La V1 doit rester simple.

Page principale :

```text
MORNING BRIEFING

Lundi 7 septembre 2026
Dernière mise à jour : 06:31

────────────────────────

ACTUALITÉ
...

MARCHÉS
...

SPORT
Football
...
Basket
...
Natation
...

SCIENCE & TECHNOLOGIE
...

MÉTÉO
Antibes | Cannes | Valbonne | Grasse
...

CITATION
...

────────────────────────

Sources
...
```

Le site doit être responsive et agréable à consulter sur ordinateur et téléphone.

L'interface doit privilégier la lisibilité plutôt que les animations.

---

# 16. Historique

La V1 doit idéalement conserver les anciens briefings.

Par exemple :

```text
/briefing/2026-09-07
/briefing/2026-09-08
/briefing/2026-09-09
```

La page principale affiche le briefing le plus récent.

Une page ou un menu permet ensuite d'accéder aux anciens briefings.

Ne pas supprimer automatiquement les anciens briefings.

---

# 17. Architecture technique

Le système doit séparer :

### Collecte
Recherche des informations.

### Analyse
Déduplication, vérification et classement.

### Génération
Création du briefing.

### Stockage
Sauvegarde du briefing sous une forme structurée, par exemple JSON.

### Frontend
Affichage du briefing.

Cette séparation est importante pour pouvoir faire évoluer le système.

---

# 18. Automatisation

Utiliser GitHub Actions ou une solution gratuite équivalente.

Workflow souhaité :

```text
06:30
  ↓
Lancement du workflow
  ↓
Recherche des informations
  ↓
Collecte
  ↓
Déduplication
  ↓
Vérification
  ↓
Classement
  ↓
Génération du briefing
  ↓
Validation minimale
  ↓
Sauvegarde
  ↓
Publication du site
```

Le workflow doit fonctionner :

- lundi ;
- mardi ;
- mercredi ;
- jeudi ;
- vendredi.

Pas besoin d'exécution le samedi et le dimanche dans la V1.

---

# 19. Coût

Objectif :

**0 €**

Ne pas intégrer de service payant obligatoire.

Le système doit privilégier :

- GitHub ;
- GitHub Actions dans les limites gratuites ;
- sources accessibles gratuitement ;
- APIs gratuites lorsqu'elles existent ;
- modèles IA gratuits ou disposant d'un quota gratuit.

Si une solution proposée nécessite une carte bancaire ou un abonnement obligatoire, elle ne doit pas devenir une dépendance de la V1.

---

# 20. Sécurité

Ne jamais mettre :

- clé API ;
- token ;
- mot de passe ;
- secret ;

directement dans le dépôt GitHub.

Utiliser les GitHub Secrets lorsque nécessaire.

Les clés ne doivent jamais apparaître dans les fichiers publics du projet.

---

# 21. Gestion des erreurs

Le système doit être robuste.

Si une source est indisponible :

→ utiliser les autres sources.

Si la recherche échoue :

→ ne pas publier de fausses informations.

Si l'IA échoue :

→ conserver le dernier briefing valide et afficher clairement que la nouvelle mise à jour n'a pas pu être générée.

Si la météo ne peut pas être récupérée :

→ ne pas inventer la météo.

Le site doit toujours privilégier le dernier contenu fiable disponible.

---

# 22. Journalisation

Le workflow doit conserver suffisamment de logs pour comprendre :

- quand la mise à jour a commencé ;
- quelles sources ont été utilisées ;
- combien d'informations ont été trouvées ;
- combien ont été retenues ;
- si une étape a échoué ;
- quand le briefing a été publié.

Cela facilitera énormément le développement et le débogage.

---

# 23. Personnalisation — PAS PRIORITAIRE EN V1

Ne pas développer immédiatement un système complexe d'apprentissage des goûts.

La V1 utilise simplement les préférences définies dans ce cahier des charges.

Dans une version ultérieure, on pourra ajouter :

- historique des lectures ;
- informations ignorées ;
- catégories préférées ;
- notation des articles ;
- apprentissage des préférences ;
- adaptation automatique de la longueur ;
- personnalisation du niveau de détail.

---

# 24. Évolutivité

Le code doit être écrit pour permettre ultérieurement :

- ajout de nouvelles catégories ;
- ajout de nouvelles sources ;
- personnalisation ;
- comptes utilisateurs ;
- plusieurs profils ;
- système de notation ;
- recherche dans les anciens briefings ;
- résumé audio éventuel ;
- notifications ;
- meilleure vérification factuelle ;
- interface plus avancée.

Mais **ne pas implémenter ces fonctionnalités maintenant**.

---

# 25. Critères de réussite de la V1

La V1 est réussie si :

1. Le site est accessible publiquement.
2. Un briefing peut être généré automatiquement.
3. Le briefing est correctement daté.
4. La dernière heure de refresh est affichée.
5. Le lundi couvre correctement le week-end.
6. Les informations sont regroupées par catégories.
7. Les doublons sont éliminés.
8. Les sources sont affichées.
9. Les informations importantes sont privilégiées.
10. Les informations non vérifiées ne sont pas présentées comme certaines.
11. Le sujet scientifique est réellement approfondi.
12. La météo couvre Antibes, Cannes, Valbonne et Grasse.
13. Les anciens briefings sont conservés.
14. Le système peut fonctionner sans intervention manuelle.
15. Le coût reste de **0 €**.

---

# 26. Consigne importante à Codex

**Ne pas chercher à construire la version finale dès maintenant.**

Commencer par analyser le dépôt existant et proposer une architecture V1 concrète.

Avant de modifier massivement le code :

1. inspecter le dépôt ;
2. identifier la stack actuelle ;
3. identifier l'hébergement ;
4. identifier les workflows GitHub Actions existants ;
5. identifier les contraintes techniques ;
6. proposer les fichiers à créer/modifier ;
7. identifier précisément les sources et APIs gratuites nécessaires ;
8. signaler les éventuelles limites de gratuité.

Ensuite seulement commencer l'implémentation.

Le système doit être conçu avec une priorité claire :

**1. Fiabilité  
2. Robustesse  
3. Qualité de sélection  
4. Qualité rédactionnelle  
5. Design  
6. Personnalisation**

La personnalisation avancée viendra plus tard.