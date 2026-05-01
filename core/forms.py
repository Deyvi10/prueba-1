from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Perfil, Torneo, Equipo, Jugador, Partido, Pago
from django.core.exceptions import ValidationError
from .models import ReservaCancha, Cupon
from .models import HorarioCancha
from .models import FotoGaleria, Publicidad

# Importamos requests para la validación del correo
import requests

# =====================================================
# 1. CREAR USUARIOS
# =====================================================
class RegistroUsuarioForm(UserCreationForm):
    rol = forms.ChoiceField(
        choices=Perfil.ROLES, 
        label="Rol del Usuario",
        widget=forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'})
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
            'email': forms.EmailInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
        }

# =====================================================
# 2. CREAR TORNEOS
# =====================================================
class TorneoForm(forms.ModelForm):
    class Meta:
        model = Torneo
        # ✨ ELIMINAMOS 'fecha_fin' DE ESTA LISTA
        fields = [
            'nombre', 
            'fecha_inicio', 
            'inscripcion_abierta', 
            'activo', 
            'costo_inscripcion', 
            'costo_amarilla', 
            'costo_roja'
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'costo_inscripcion': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'costo_amarilla': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'costo_roja': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
# =====================================================
# 3. CREAR EQUIPOS 
# =====================================================


class EquipoSolicitudForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['nombre', 'escudo', 'nombre_suplente_1', 'nombre_suplente_2'] # SIN CAMPOS DE ADMIN
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Los Rayados FC'}),
            'escudo': forms.FileInput(attrs={'class': 'form-control'}),
            'nombre_suplente_1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del Suplente 1 (Opcional)'}),
            'nombre_suplente_2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del Suplente 2 (Opcional)'}),
            'telefono_contacto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 0964049283', 'required': 'True'}),   
        }

        
class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['nombre', 'escudo', 'nombre_suplente_1', 'nombre_suplente_2', 'estado_inscripcion', 'puede_fichar']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Los Rayados FC'}),
            'escudo': forms.FileInput(attrs={'class': 'form-control'}),
            'nombre_suplente_1': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_suplente_2': forms.TextInput(attrs={'class': 'form-control'}),
            'estado_inscripcion': forms.Select(attrs={'class': 'form-select fw-bold border-secondary'}),
            'puede_fichar': forms.CheckboxInput(attrs={'class': 'form-check-input fs-4 shadow-sm border-secondary', 'role': 'switch'}),
        }
        labels = {
            'estado_inscripcion': 'Estado en el Torneo',
            'puede_fichar': '🟢 ¿Permitir que este equipo fiche jugadores?'
        }

class JugadorForm(forms.ModelForm):
    class Meta:
        model = Jugador
        fields = ['equipo', 'nombres', 'dorsal', 'cedula', 'foto']
        widgets = {
            'equipo': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'placeholder': 'Ej: Enner Valencia'}),
            'dorsal': forms.NumberInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'placeholder': 'Ej: 13'}),
            'cedula': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'placeholder': 'Cédula / DNI'}),
            'foto': forms.FileInput(attrs={'class': 'form-control bg-dark text-white border-secondary'}),
        }

# =====================================================
# 5. PROGRAMAR PARTIDOS
# =====================================================
class ProgramarPartidoForm(forms.ModelForm):
    class Meta:
        model = Partido
        # Agregamos 'numero_fecha' para poder agrupar por Jornadas
        fields = ['torneo', 'numero_fecha', 'etapa', 'equipo_local', 'equipo_visita', 'fecha_hora', 'cancha']
        
        widgets = {
            'torneo': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'numero_fecha': forms.NumberInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'placeholder': 'Ej: 1', 'min': '1'}),
            'etapa': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'equipo_local': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'equipo_visita': forms.Select(attrs={'class': 'form-select bg-dark text-white border-secondary'}),
            'fecha_hora': forms.DateTimeInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'type': 'datetime-local'}),
            'cancha': forms.TextInput(attrs={'class': 'form-control bg-dark text-white border-secondary', 'placeholder': 'Ej: Cancha Principal'}),
        }
        
        labels = {
            'numero_fecha': 'Jornada N°',
            'equipo_local': 'Equipo A (Local)',
            'equipo_visita': 'Equipo B (Visita)',
        }

    def clean(self):
        cleaned_data = super().clean()
        # Usamos .get() para evitar errores si el campo viene vacío
        local = cleaned_data.get("equipo_local")
        visita = cleaned_data.get("equipo_visita")

        # 1. VALIDACIÓN: Mismo equipo
        if local and visita and local == visita:
            # Esto agrega el error ESPECÍFICAMENTE al campo, para que salga rojo y con mensaje
            self.add_error('equipo_visita', "⛔ ERROR: Un equipo no puede jugar contra sí mismo.")
            self.add_error('equipo_local', "⛔ Selecciona equipos diferentes.")
            
            # Y esto lanza un error general por si acaso
            raise forms.ValidationError("Error de Lógica: El partido no puede ser entre el mismo equipo.")
        
        return cleaned_data
    

# =====================================================
# 6. FINANZAS Y PAGOS 
# =====================================================
class PagoForm(forms.ModelForm):
    class Meta:
        model = Pago
    
        fields = ['equipo', 'monto', 'fecha', 'comprobante', 'observacion']
        
        widgets = {
            
            'equipo': forms.Select(attrs={
                'class': 'form-select bg-white text-dark border-secondary-subtle'
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control bg-white text-dark border-secondary-subtle', 
                'placeholder': '0.00'
            }),
            'fecha': forms.DateInput(attrs={
                'class': 'form-control bg-white text-dark border-secondary-subtle', 
                'type': 'date'
            }),
            'comprobante': forms.FileInput(attrs={
                'class': 'form-control bg-white text-dark border-secondary-subtle'
            }),
            'observacion': forms.Textarea(attrs={
                'class': 'form-control bg-white text-dark border-secondary-subtle', 
                'rows': 2, 
                'placeholder': 'Ej: Abono inscripción / Pago de multa fecha 3'
            }),
        }
        labels = {
            'equipo': 'Equipo que realiza el pago',
            'monto': 'Valor a pagar ($)',
            'comprobante': 'Imagen del depósito/transferencia',
            'observacion': 'Notas adicionales'
        }

    def clean(self):
        cleaned_data = super().clean()
        monto = cleaned_data.get('monto')
        equipo = cleaned_data.get('equipo')

        # 1. Validamos que el monto no sea nulo para empezar
        if monto is not None:
            
            # 2. VALIDACIÓN: No aceptar negativos ni ceros
            if monto <= 0:
                self.add_error('monto', "El monto debe ser mayor a $0. No se permiten valores negativos o nulos.")
            
            # 3. VALIDACIÓN DE NEGOCIO: No pagar más de la deuda real
            elif equipo:
                deuda_actual = equipo.deuda_pendiente()
                
                # Caso: Equipo ya no debe nada
                if deuda_actual <= 0:
                    self.add_error('equipo', f"El equipo {equipo.nombre} ya se encuentra al día con sus pagos.")
                
                # Caso: Intenta pagar más de lo que debe
                elif monto > deuda_actual:
                    self.add_error('monto', f"Operación denegada: El equipo solo adeuda ${deuda_actual}. No puedes registrar un pago por ${monto}.")

        return cleaned_data

class RegistroPublicoForm(UserCreationForm):
    first_name = forms.CharField(label="Nombres", required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label="Apellidos", required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label="Correo Electrónico", required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    telefono = forms.CharField(label="Teléfono", required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        if not email:
            return email

        # ✨ MAGIA DE VALIDACIÓN DE CORREO REAL (API) ✨
        # Reemplaza "TU_CLAVE_API_AQUI" por tu API Key de AbstractAPI
        api_key = "TU_CLAVE_API_AQUI"
        url = f"https://emailvalidation.abstractapi.com/v1/?api_key={api_key}&email={email}"
        
        try:
            # Ponemos un timeout de 3 segundos para que la página no se quede congelada si la API tarda
            respuesta = requests.get(url, timeout=3)
            
            if respuesta.status_code == 200:
                datos = respuesta.json()
                
                # Si el correo va a rebotar (es inventado)
                if datos.get('deliverability') == "UNDELIVERABLE":
                    raise ValidationError("Este correo electrónico no existe o es falso. Usa uno real.")
                
                # Bloqueo extra: Rechazar correos temporales (opcional)
                if datos.get('is_disposable_email', {}).get('value') == True:
                    raise ValidationError("No se permiten direcciones de correo temporales.")
                    
        except requests.exceptions.RequestException:
            # Si falla el internet o la API, dejamos pasar el registro para no bloquear a los usuarios
            pass
            
        return email

    def save(self, commit=True):
        # 1. Guardamos el usuario (Esto dispara la señal automática si existe)
        user = super().save(commit=True)

        # 2. Manejo Seguro del Perfil
        # Intentamos obtener el perfil si la señal ya lo creó.
        if hasattr(user, 'perfil'):
            perfil = user.perfil
        else:
            perfil = Perfil.objects.create(usuario=user)
        
        # 3. Actualizamos los datos extra
        perfil.telefono = self.cleaned_data.get('telefono')
        perfil.rol = 'FAN'  # Rol por defecto para gente de internet
        perfil.save()
        
        # 4. Actualizar datos del usuario base
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            
        return user
    
class ReservaCanchaForm(forms.ModelForm):
    codigo_cupon = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': '¿Tienes un código de descuento?'
    }))

    class Meta:
        model = ReservaCancha
        fields = ['fecha', 'hora_inicio', 'hora_fin']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fin': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        codigo = cleaned_data.get('codigo_cupon')
        
        # Validar Cupón si escribieron algo
        if codigo:
            try:
                cupon = Cupon.objects.get(codigo=codigo)
                if not cupon.es_valido():
                    self.add_error('codigo_cupon', 'Este cupón ha expirado o ya no es válido.')
                # Guardamos el objeto cupón en "cleaned_data" para usarlo en la vista
                cleaned_data['objeto_cupon'] = cupon
            except Cupon.DoesNotExist:
                self.add_error('codigo_cupon', 'Código de cupón incorrecto.')
        
        return cleaned_data

class HorarioCanchaForm(forms.ModelForm):
    class Meta:
        model = HorarioCancha
        fields = ['hora_inicio', 'hora_fin', 'precio', 'activo']
        widgets = {
            'hora_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fin': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'step': '0.50', 'class': 'form-control', 'placeholder': 'Ej: 5.00'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('hora_inicio')
        fin = cleaned_data.get('hora_fin')

        if inicio and fin:
            if inicio >= fin:
                raise ValidationError("La hora de inicio debe ser más temprano que la hora de fin.")

            # 🛡️ ESCUDO ANTI-CHOQUES: Verifica si la hora se cruza con una que ya existe
            cruces = HorarioCancha.objects.filter(
                hora_inicio__lt=fin,
                hora_fin__gt=inicio
            )
            
            if self.instance and self.instance.pk:
                cruces = cruces.exclude(pk=self.instance.pk)

            if cruces.exists():
                raise ValidationError("⛔ Ya tienes otra tarifa configurada en este horario. Revisa los cruces.")

        return cleaned_data
    

class FotoGaleriaForm(forms.ModelForm):
    class Meta:
        model = FotoGaleria
        fields = ['imagen', 'titulo', 'orden', 'activa']
        widgets = {
            'imagen': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Cancha principal iluminada'}),
            'orden': forms.NumberInput(attrs={'class': 'form-control'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class PublicidadForm(forms.ModelForm):
    # Cambiamos el campo a Texto normal para que el navegador no te obligue a escribir "http://"
    enlace = forms.CharField(
        required=False,
        label="Número de WhatsApp o Link",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 0991234567 o un link a Facebook'})
    )

    class Meta:
        model = Publicidad
        fields = ['imagen', 'empresa', 'enlace', 'activa']
        
    def clean_enlace(self):
        enlace = self.cleaned_data.get('enlace')
        
        if enlace:
            enlace = enlace.strip().replace(" ", "") # Quitamos espacios por si acaso
            
            # ✨ LA MAGIA: Si escribiste exactamente 10 números y empieza con '0'
            if enlace.isdigit() and len(enlace) == 10 and enlace.startswith('0'):
                numero_limpio = enlace[1:] # Le quitamos el primer '0'
                return f"https://wa.me/593{numero_limpio}"
            
            # Si pegaste un link normal pero olvidaste el http://
            elif not enlace.startswith('http://') and not enlace.startswith('https://'):
                return f"https://{enlace}"
                
        return enlace