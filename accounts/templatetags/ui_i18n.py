"""Traducciones explícitas de la interfaz propia del proyecto.

Django ya traduce su administrador. Este catálogo pequeño cubre la interfaz
hecha a medida y mantiene el castellano como fuente legible y auditable.
"""

from django import template
from django.utils.translation import get_language


register = template.Library()


_T = {
    'teacher_panel': {'es': 'Panel docente', 'en': 'Teacher panel', 'fr': 'Espace enseignant', 'de': 'Lehrbereich'},
    'reviews': {'es': 'Correcciones', 'en': 'Reviews', 'fr': 'Corrections', 'de': 'Korrekturen'},
    'analytics': {'es': 'Analíticas', 'en': 'Analytics', 'fr': 'Analyses', 'de': 'Analysen'},
    'home': {'es': 'Inicio', 'en': 'Home', 'fr': 'Accueil', 'de': 'Start'},
    'my_history': {'es': 'Mi historial', 'en': 'My history', 'fr': 'Mon historique', 'de': 'Mein Verlauf'},
    'log_out': {'es': 'Salir', 'en': 'Log out', 'fr': 'Se déconnecter', 'de': 'Abmelden'},
    'log_in': {'es': 'Iniciar sesión', 'en': 'Log in', 'fr': 'Se connecter', 'de': 'Anmelden'},
    'teacher': {'es': 'docente', 'en': 'teacher', 'fr': 'enseignant·e', 'de': 'Lehrkraft'},
    'student': {'es': 'estudiante', 'en': 'student', 'fr': 'étudiant·e', 'de': 'Lernende'},
    'commissions': {'es': 'Comisiones', 'en': 'Classes', 'fr': 'Groupes', 'de': 'Kurse'},
    'pending_reviews': {'es': 'Correcciones pendientes', 'en': 'Pending reviews', 'fr': 'Corrections en attente', 'de': 'Offene Korrekturen'},
    'new_class': {'es': '+ Comisión', 'en': '+ Class', 'fr': '+ Groupe', 'de': '+ Kurs'},
    'new_practice': {'es': '+ Práctica', 'en': '+ Practice', 'fr': '+ Activité', 'de': '+ Übung'},
    'new_exercise': {'es': '+ Ejercicio', 'en': '+ Exercise', 'fr': '+ Exercice', 'de': '+ Aufgabe'},
    'language': {'es': 'Idioma', 'en': 'Language', 'fr': 'Langue', 'de': 'Sprache'},
    'username': {'es': 'Usuario', 'en': 'Username', 'fr': 'Identifiant', 'de': 'Benutzername'},
    'password': {'es': 'Contraseña', 'en': 'Password', 'fr': 'Mot de passe', 'de': 'Passwort'},
    'enter': {'es': 'Entrar', 'en': 'Enter', 'fr': 'Entrer', 'de': 'Anmelden'},
    'bad_login': {'es': 'Usuario o contraseña incorrectos. Intentá de nuevo.', 'en': 'Incorrect username or password. Please try again.', 'fr': 'Identifiant ou mot de passe incorrect. Réessayez.', 'de': 'Benutzername oder Passwort falsch. Bitte erneut versuchen.'},
    'account_from_class_link': {'es': 'Si no tenés cuenta, ingresá desde el link de tu comisión para registrarte.', 'en': 'If you do not have an account, use your class link to register.', 'fr': 'Si vous n’avez pas de compte, utilisez le lien de votre groupe pour vous inscrire.', 'de': 'Wenn du noch kein Konto hast, registriere dich über den Link deines Kurses.'},
    'my_practices': {'es': 'Mis prácticas', 'en': 'My practices', 'fr': 'Mes activités', 'de': 'Meine Übungen'},
    'view_attempt_history': {'es': 'Ver mi historial de intentos', 'en': 'View my attempt history', 'fr': 'Voir mon historique de tentatives', 'de': 'Meine Versuche ansehen'},
    'not_enrolled': {'es': 'Todavía no estás inscripto en ninguna comisión. Pedíselo a tu docente.', 'en': 'You are not enrolled in any class yet. Ask your teacher.', 'fr': 'Vous n’êtes encore inscrit·e dans aucun groupe. Demandez à votre enseignant·e.', 'de': 'Du bist noch in keinem Kurs eingeschrieben. Frage deine Lehrkraft.'},
    'class_no_practices': {'es': 'Esta comisión todavía no tiene prácticas.', 'en': 'This class has no practices yet.', 'fr': 'Ce groupe n’a pas encore d’activités.', 'de': 'Dieser Kurs hat noch keine Übungen.'},
    'not_available_yet': {'es': 'No disponible aún', 'en': 'Not available yet', 'fr': 'Pas encore disponible', 'de': 'Noch nicht verfügbar'},
    'closed': {'es': 'Cerrada', 'en': 'Closed', 'fr': 'Fermée', 'de': 'Geschlossen'},
    'completed': {'es': 'Completada', 'en': 'Completed', 'fr': 'Terminée', 'de': 'Abgeschlossen'},
    'in_progress': {'es': 'En curso', 'en': 'In progress', 'fr': 'En cours', 'de': 'In Bearbeitung'},
    'not_started': {'es': 'Sin iniciar', 'en': 'Not started', 'fr': 'Non commencée', 'de': 'Nicht begonnen'},
    'opens': {'es': 'Abre', 'en': 'Opens', 'fr': 'Ouvre', 'de': 'Öffnet'},
    'closed_on': {'es': 'Cerró', 'en': 'Closed', 'fr': 'Fermée', 'de': 'Geschlossen'},
    'closes': {'es': 'Cierra', 'en': 'Closes', 'fr': 'Ferme', 'de': 'Schließt'},
    'teacher_comments': {'es': 'Intentos con comentario docente', 'en': 'Attempts with teacher feedback', 'fr': 'Tentatives commentées par l’enseignant·e', 'de': 'Versuche mit Rückmeldung'},
    'approved': {'es': 'Aprobado', 'en': 'Approved', 'fr': 'Approuvé', 'de': 'Bestätigt'},
    'rejected': {'es': 'Rechazado', 'en': 'Rejected', 'fr': 'Rejeté', 'de': 'Abgelehnt'},
    'your_answer': {'es': 'Tu respuesta', 'en': 'Your answer', 'fr': 'Votre réponse', 'de': 'Deine Antwort'},
    'show_more': {'es': 'Ver más', 'en': 'Show more', 'fr': 'Voir plus', 'de': 'Mehr anzeigen'},
    'class': {'es': 'Comisión', 'en': 'Class', 'fr': 'Groupe', 'de': 'Kurs'},
    'practice_no_exercises': {'es': 'Esta práctica todavía no tiene ejercicios.', 'en': 'This practice has no exercises yet.', 'fr': 'Cette activité n’a pas encore d’exercices.', 'de': 'Diese Übung hat noch keine Aufgaben.'},
    'exercise': {'es': 'Ejercicio', 'en': 'Exercise', 'fr': 'Exercice', 'de': 'Aufgabe'},
    'fix': {'es': 'Corregir', 'en': 'Revise', 'fr': 'Corriger', 'de': 'Überarbeiten'},
    'solve': {'es': 'Resolver', 'en': 'Solve', 'fr': 'Résoudre', 'de': 'Lösen'},
    'practice_unavailable': {'es': 'Práctica aún no disponible', 'en': 'Practice not available yet', 'fr': 'Activité pas encore disponible', 'de': 'Übung noch nicht verfügbar'},
    'practice_closed': {'es': 'Práctica cerrada', 'en': 'Practice closed', 'fr': 'Activité fermée', 'de': 'Übung geschlossen'},
    'back_home': {'es': 'Volver al inicio', 'en': 'Back to home', 'fr': 'Retour à l’accueil', 'de': 'Zurück zum Start'},
    'download_zip': {'es': 'Descargar ZIP', 'en': 'Download ZIP', 'fr': 'Télécharger le ZIP', 'de': 'ZIP herunterladen'},
    'install_package': {'es': 'Instalar paquete', 'en': 'Install package', 'fr': 'Installer un paquet', 'de': 'Paket installieren'},
    'install_zip': {'es': 'Instalar ZIP', 'en': 'Install ZIP', 'fr': 'Installer le ZIP', 'de': 'ZIP installieren'},
    'view': {'es': 'Ver', 'en': 'View', 'fr': 'Voir', 'de': 'Ansehen'},
    'edit': {'es': 'Editar', 'en': 'Edit', 'fr': 'Modifier', 'de': 'Bearbeiten'},
    'delete': {'es': 'Eliminar', 'en': 'Delete', 'fr': 'Supprimer', 'de': 'Löschen'},
    'practice_bank': {'es': 'Banco de prácticas', 'en': 'Practice library', 'fr': 'Bibliothèque d’activités', 'de': 'Übungsbibliothek'},
    'exercise_bank': {'es': 'Banco de ejercicios', 'en': 'Exercise library', 'fr': 'Bibliothèque d’exercices', 'de': 'Aufgabenbibliothek'},
    'setup_title': {'es': 'Asistente de instalación', 'en': 'Setup assistant', 'fr': 'Assistant d’installation', 'de': 'Installationsassistent'},
    'complete_setup': {'es': 'Completar instalación', 'en': 'Complete setup', 'fr': 'Terminer l’installation', 'de': 'Installation abschließen'},
}


@register.simple_tag
def ui(key):
    idioma = (get_language() or 'es').split('-')[0]
    traducciones = _T.get(key)
    if traducciones is None:
        return key
    return traducciones.get(idioma) or traducciones['es']
