import json
import os
import logging
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

import os

# --- CONFIGURATION DES CLEFS (Via le Cloud ou l'environnement) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

client = Groq(api_key=GROQ_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Dossier pour stocker la mémoire de chaque utilisateur
DOSSIER_MEMOIRE = "memoires_utilisateurs"
if not os.path.exists(DOSSIER_MEMOIRE):
    os.makedirs(DOSSIER_MEMOIRE)


def charger_historique(user_id):
    """Charge l'historique d'un utilisateur depuis un fichier JSON."""
    chemin_fichier = os.path.join(DOSSIER_MEMOIRE, f"{user_id}.json")
    if os.path.exists(chemin_fichier):
        with open(chemin_fichier, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # Premier lancement pour cet utilisateur : on met le System Prompt
        return [
            {
                "role": "system",
                "content": "Tu es un assistant personnel intelligent et un peu sarcastique sur Telegram.",
            }
        ]


def sauvegarder_historique(user_id, historique):
    """Sauvegarde l'historique dans un fichier JSON."""
    chemin_fichier = os.path.join(DOSSIER_MEMOIRE, f"{user_id}.json")
    with open(chemin_fichier, "w", encoding="utf-8") as f:
        json.dump(historique, f, ensure_ascii=False, indent=4)


# --- TON OUTIL ---
def calculer_surface(longueur, largeur):
    """Calcule la surface d'une pièce en fonction de sa longueur et largeur."""
    surface = longueur * largeur
    return json.dumps({"surface_m2": surface})


outils_disponibles = [
    {
        "type": "function",
        "function": {
            "name": "calculer_surface",
            "description": "Calcule strictement la surface en m2 d'une pièce connaissant sa longueur et sa largeur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "longueur": {"type": "number", "description": "La longueur en mètres"},
                    "largeur": {"type": "number", "description": "La largeur en mètres"},
                },
                "required": ["longueur", "largeur"],
            },
        },
    }
]


# --- GESTION DES MESSAGES AVEC MÉMOIRE PERSISTANTE ---
async def repondre_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id  # L'ID unique de l'utilisateur Telegram
    texte_utilisateur = update.message.text
    print(f"Message de {user_id} : {texte_utilisateur}")

    # 1. On charge la mémoire de cet utilisateur
    historique = charger_historique(user_id)

    # 2. On ajoute son nouveau message à l'historique
    historique.append({"role": "user", "content": texte_utilisateur})

    # 3. On envoie tout à l'IA
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=historique,
        tools=outils_disponibles,
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    # 4. Gestion de l'outil si l'IA en a besoin
    if response_message.tool_calls:
        print("🧠 L'IA utilise l'outil !")
        for tool_call in response_message.tool_calls:
            nom_fonction = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if nom_fonction == "calculer_surface":
                resultat_brut = calculer_surface(
                    longueur=args["longueur"], largeur=args["largeur"]
                )

                historique.append(response_message)
                historique.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": nom_fonction,
                        "content": resultat_brut,
                    }
                )

                response_finale = client.chat.completions.create(
                    model="openai/gpt-oss-120b", messages=historique
                )
                bot_reponse = response_finale.choices[0].message.content
    else:
        bot_reponse = response_message.content

    # 5. On ajoute la réponse du bot dans l'historique et on sauvegarde dans le fichier JSON
    historique.append({"role": "assistant", "content": bot_reponse})
    sauvegarder_historique(user_id, historique)

    # 6. On répond sur Telegram
    await update.message.reply_text(bot_reponse)


if __name__ == "__main__":
    print("🤖 Le bot Telegram avec mémoire persistante est en ligne !")
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), repondre_message)
    )
    application.run_polling()
