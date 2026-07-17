from django.db import migrations

def grandfather_users(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    Usuario.objects.all().update(estado_aprobacion='aprobado')

class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_usuario_estado_aprobacion'),
    ]

    operations = [
        migrations.RunPython(grandfather_users),
    ]
