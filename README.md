# Screener CAC Small

Chaque soir de semaine, après la clôture de la Bourse de Paris, ce bot analyse les valeurs du **CAC Small** (petites capitalisations de la Bourse de Paris) via l'API de Yahoo Finance et t'envoie un e-mail qui ne contient **que les valeurs qui méritent ton attention** :

- **Achat à étudier** : configuration technique favorable et score élevé ;
- **À surveiller** : configuration intéressante mais pas encore confirmée.

Les autres valeurs sont écartées. S'il n'y a rien d'intéressant, le mail le dit en une ligne.

Pour chaque valeur retenue : cours, raisons de la sélection, graphique sur 9 mois (moyennes mobiles 50/200 jours), stop et objectif indicatifs, consensus des analystes, alerte si les résultats tombent dans les 10 jours.

Le mail contient les graphiques en image. Le **rapport en pièce jointe** (fichier `.html` à ouvrir dans ton navigateur) a les mêmes graphiques en version **interactive** : en passant la souris (ou le doigt) sur la courbe, tu vois la date, le cours de clôture exact, la variation de la séance et les moyennes mobiles.

Il tourne gratuitement sur **GitHub Actions** : rien à laisser allumé.

> ⚠️ Sélection automatique fondée sur des indicateurs techniques et le consensus des analystes. Ce sont des pistes à étudier, pas des conseils financiers.

---

## 1. Mise en route (une seule fois)

### a) Mot de passe d'application Gmail
1. Active la validation en deux étapes sur ton compte Google.
2. Va sur <https://myaccount.google.com/apppasswords>, crée un mot de passe nommé `screener-cac40` (ou réutilise celui de `bot-bourse`).
3. Copie les 16 caractères.

### b) Secrets GitHub
Dans ce dépôt : **Settings → Secrets and variables → Actions → New repository secret** :

| Nom | Valeur |
|---|---|
| `SMTP_USER` | ton adresse Gmail (l'expéditeur) |
| `SMTP_PASSWORD` | le mot de passe d'application de 16 caractères |
| `EMAIL_TO` | l'adresse qui reçoit le rapport |

Les secrets sont propres à chaque dépôt : il faut les recréer ici même s'ils existent déjà dans `bot-bourse`.

### c) Tester
**Actions → Screener CAC Small quotidien → Run workflow**. Le mail arrive en 1 à 2 minutes.

Ensuite il part automatiquement **du lundi au vendredi à 18 h 15** (heure de Paris, 19 h 15 en été).

---

## 2. Comment une valeur est sélectionnée

Une valeur n'est retenue que si elle est **assez liquide** (au moins 150 000 € échangés par séance en moyenne sur 20 jours : en dessous, acheter ou revendre peut coûter cher) et présente **au moins une configuration** :

| Configuration | Points |
|---|---|
| Repli en tendance haussière : cours > MM200 (en hausse), MM50 > MM200, RSI entre 35 et 50, cours revenu près de la MM50 | +3 |
| Cassure du plus haut 52 semaines avec du volume | +3 |
| Cassure du plus haut 3 mois avec un volume ≥ 1,5× la moyenne | +2 |
| Croisement en or récent (MM50 passe au-dessus de la MM200) | +2 |
| Retour au-dessus de la MM200 avec du volume | +2 |
| Rebond après survente (RSI repasse au-dessus de 30) | +2 |

Puis bonus et malus :

| Critère | Points |
|---|---|
| Surperforme l'indice d'au moins 5 points sur 3 mois / sous-performe de 10 points | +1 / −1 |
| MACD qui recroise son signal à la hausse | +1 |
| Objectif des analystes ≥ 15 % au-dessus du cours (au moins 3 analystes) / déjà dépassé | +1 / −1 |
| Consensus des analystes à la vente | −1 |
| RSI > 72 (surachat) | −2 |
| MM200 orientée à la baisse, cours en dessous | −1 |

**Score ≥ 4** (et cours au-dessus de la MM200, pas en surachat) donne **Achat à étudier**, **score ≥ 2** donne **À surveiller**. Au plus 5 valeurs par catégorie, classées par score.

Le **stop indicatif** est placé à 2 ATR (volatilité moyenne sur 14 jours) sous le cours. L'**objectif** reprend le consensus des analystes, ou vise 2 fois le risque pris.

Yahoo Finance ne publiant pas l'indice CAC Small, la référence est la **moyenne équipondérée** des valeurs analysées. Le mail rappelle sa tendance et la part des valeurs au-dessus de leur MM200. Si le marché est fragile, il le signale.

---

## 3. La liste des valeurs (mise à jour automatique)

La liste est dans **`univers.json`**. Chaque lundi matin, le workflow **« Mise à jour de la composition du CAC Small »** la reconstruit et l'enregistre si elle a changé :

1. **Euronext** : le PDF officiel de composition. La version gratuite ne donne que les plus grosses valeurs (37 au 30/09/2026, plus de 80 % du poids de l'indice). La liste complète est réservée aux clients sous licence d'Euronext.
2. **Wikipédia** : le modèle « Palette CAC Small » liste les autres sociétés de l'indice. Leur ticker Paris est retrouvé automatiquement avec la recherche de Yahoo Finance.

Pour forcer une mise à jour : **Actions → Mise à jour de la composition du CAC Small → Run workflow**. Les sociétés dont le ticker n'a pas été trouvé sont listées dans `univers.json` (`non_trouvees`).

## 3. Personnaliser

Tout se règle dans **`config.json`** (modifiable sur github.com avec l'icône crayon) :

- `indice` : nom de l'indice et ticker Yahoo de la référence (vide = moyenne équipondérée).
- `selection` : scores minimaux et nombre maximal de valeurs par catégorie.
- `seuils` : RSI, volume de cassure, fenêtre d'alerte avant résultats, distance du stop, liquidité minimale (`liquidite_min_eur`), nombre minimal d'analystes.

Pour changer la logique, modifie `detect_setups` dans `screener/analysis.py`.

## 4. Lancer sur ton ordinateur

```bash
pip install -r requirements.txt
python -m screener --no-email          # vraies données, rapport dans reports/ sans envoi
python -m screener --demo --no-email   # données simulées, sans Internet
```

## Structure

```
config.json             indice de référence, scores et seuils
univers.json            valeurs du CAC Small (généré automatiquement)
tools/update_universe.py  mise à jour de univers.json
screener/data.py        cours et consensus via Yahoo Finance (yfinance)
screener/analysis.py    indicateurs, configurations, score, sélection
screener/charts.py      graphique 9 mois (image du mail)
screener/interactive.py graphique interactif du rapport joint
screener/report.py      e-mail / rapport HTML (valeurs retenues uniquement)
screener/mailer.py      envoi SMTP, graphiques intégrés au mail
.github/workflows/      planification quotidienne
```
