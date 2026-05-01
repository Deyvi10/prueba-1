from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, time, datetime
from django.db.models import Sum, Q
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# =====================================================
# --- VALIDADORES PERSONALIZADOS ---
# =====================================================
def validar_cedula_db(value):
    if len(value) != 10 or not value.isdigit():
        raise ValidationError("La cédula debe tener exactamente 10 dígitos numéricos.")
    provincia = int(value[0:2])
    if provincia < 1 or provincia > 24:
        raise ValidationError("Código de provincia inválido.")
    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = sum([
        (int(value[i]) * coeficientes[i] if int(value[i]) * coeficientes[i] < 10 
         else int(value[i]) * coeficientes[i] - 9) 
        for i in range(9)
    ])
    digito = int(value[9])
    calculado = (total + 9) // 10 * 10 - total
    if calculado == 10: calculado = 0
    if calculado != digito:
        raise ValidationError("La cédula ecuatoriana ingresada no es matemáticamente válida.")

validador_letras = RegexValidator(
    regex=r'^[a-zA-ZñÑáéíóúÁÉÍÓÚ\s]+$', 
    message='El nombre solo puede contener letras y espacios. No se permiten números ni símbolos.'
)

# =====================================================
# 1. USUARIOS Y PERFILES
# =====================================================
class Perfil(models.Model):
    ROLES = [
        ('ORG', 'Organizador'),         # Dueño del sistema
        ('VOC', 'Vocal de Mesa'),       # Ayudante
        ('DIR', 'Dirigente de Equipo'), # Cliente Torneo
        ('FAN', 'Aficionado / Cliente'),# Cliente Cancha / Espectador
    ]
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=3, choices=ROLES, default='FAN') 
    telefono = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='perfiles/', blank=True, null=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.get_rol_display()}"

# =====================================================
# 2. CUPONES DE DESCUENTO
# =====================================================
class Cupon(models.Model):
    TIPO_CUPON = (
        ('CANCHA', 'Alquiler de Cancha'),
        ('TORNEO', 'Inscripción de Campeonato'),
    )
    codigo = models.CharField(max_length=20, unique=True, help_text="Ej: GOLAZO2026")
    descuento = models.DecimalField(max_digits=5, decimal_places=2, help_text="Monto en $ a descontar")
    tipo = models.CharField(max_length=15, choices=TIPO_CUPON)
    activo = models.BooleanField(default=True)
    
    usos_actuales = models.PositiveIntegerField(default=0)
    limite_usos = models.PositiveIntegerField(null=True, blank=True, help_text="Dejar vacío para ilimitado")
    fecha_expiracion = models.DateField(null=True, blank=True)

    def es_valido(self):
        ahora = timezone.now().date()
        if not self.activo: return False
        if self.fecha_expiracion and ahora > self.fecha_expiracion: return False
        if self.limite_usos and self.usos_actuales >= self.limite_usos: return False
        return True

    def __str__(self):
        return f"CUPÓN: {self.codigo} (-${self.descuento})"

# =====================================================
# 3. TORNEOS
# =====================================================
class Torneo(models.Model):
    nombre = models.CharField(max_length=100)
    organizador = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_inicio = models.DateField(default=timezone.now)
    activo = models.BooleanField(default=True)
    costo_inscripcion = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    costo_amarilla = models.DecimalField(max_digits=5, decimal_places=2, default=0.50, verbose_name="Multa Amarilla ($)")
    costo_roja = models.DecimalField(max_digits=5, decimal_places=2, default=5.00, verbose_name="Multa Roja ($)")
    
    inscripcion_abierta = models.BooleanField(default=True, verbose_name="¿Inscripción Habilitada?")
    fecha_limite_inscripcion = models.DateField(null=True, blank=True)

    # ✨ NUEVOS CAMPOS: CONFIGURACIÓN DE IDA Y VUELTA
    fase2_ida_vuelta = models.BooleanField(default=False, verbose_name="Fase 2 (Grupos) - Ida y Vuelta")
    fase3_ida_vuelta = models.BooleanField(default=False, verbose_name="Fase 3 (Cuartos) - Ida y Vuelta")

    def __str__(self):
        return self.nombre

    @property
    def periodo_valido(self):
        if self.fecha_limite_inscripcion:
            return date.today() <= self.fecha_limite_inscripcion
        return True

# =====================================================
# 4. EQUIPOS
# =====================================================
class Equipo(models.Model):
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE, related_name='equipos')
    dirigente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='equipo_dirigido')
    nombre = models.CharField(max_length=100)
    escudo = models.ImageField(upload_to='escudos/', null=True, blank=True)
    telefono_contacto = models.CharField(max_length=15, blank=True, null=True, verbose_name="Celular de Contacto")
    nombre_suplente_1 = models.CharField(max_length=100, blank=True)
    nombre_suplente_2 = models.CharField(max_length=100, blank=True)
    pagado = models.BooleanField(default=False, verbose_name="Inscripción Pagada")
    monto_reembolso = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    puntos_bonificacion = models.IntegerField(default=0)
    GRUPO_FASE2_CHOICES = [('A', 'Grupo A'), ('B', 'Grupo B'), ('N', 'Ninguno')]
    grupo_fase2 = models.CharField(max_length=1, choices=GRUPO_FASE2_CHOICES, default='N')

    ESTADOS_INSCRIPCION = [
        ('PENDIENTE', '⏳ Pendiente de Aprobación'),
        ('APROBADO', '✅ Aprobado'),
        ('RECHAZADO', '❌ Rechazado'),
    ]
    estado_inscripcion = models.CharField(max_length=10, choices=ESTADOS_INSCRIPCION, default='PENDIENTE')
    puede_fichar = models.BooleanField(default=False, verbose_name="¿Permiso para Fichar?")

    def __str__(self):
        return self.nombre
    
    # --- MÉTODOS FINANCIEROS UNIFICADOS ---
    def total_pagado(self):
        resultado = self.pagos.aggregate(total=Sum('monto'))['total']
        return resultado or 0

    def total_multas(self):
        resultado = self.sanciones.aggregate(total=Sum('monto'))['total']
        return resultado or 0

    def deuda_pendiente(self):
        valor_inscripcion = self.torneo.costo_inscripcion
        multas = self.total_multas()
        pagado = self.total_pagado()
        return (valor_inscripcion + multas) - pagado
    
    def tiene_deudas(self):
        return self.total_deuda() > 0

    def total_deuda(self):
        total = self.sanciones.filter(pagada=False).aggregate(Sum('monto'))['monto__sum']
        return total or 0.00

# =====================================================
# 5. PAGOS
# =====================================================
class Pago(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=date.today)
    comprobante = models.ImageField(upload_to='pagos/', null=True, blank=True)
    validado = models.BooleanField(default=False)
    observacion = models.TextField(max_length=500, blank=True, null=True)
    
    def __str__(self):
        return f"Abono ${self.monto} - {self.equipo.nombre}"

# =====================================================
# 6. JUGADORES (BLINDADO)
# =====================================================
class Jugador(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='jugadores')
    nombres = models.CharField(max_length=100, validators=[validador_letras])
    dorsal = models.PositiveIntegerField()
    cedula = models.CharField(max_length=15, unique=True, validators=[validar_cedula_db])
    foto = models.ImageField(upload_to='jugadores/', null=True, blank=True)
    rojas_directas_acumuladas = models.PositiveIntegerField(default=0)
    expulsado_torneo = models.BooleanField(default=False)
    partidos_suspension = models.IntegerField(default=0, verbose_name="Partidos de Suspensión")
    
    # 🔥 AGREGA ESTA LÍNEA AQUÍ:
    es_refuerzo = models.BooleanField(default=False, verbose_name="¿Es Refuerzo?")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['equipo', 'dorsal'], name='unico_dorsal_por_equipo')
        ]

    def __str__(self):
        return f"{self.nombres} ({self.dorsal})"
    
    @property
    def esta_habilitado(self):
        return self.partidos_suspension <= 0 and not self.expulsado_torneo

# =====================================================
# 7. PARTIDOS (FIXTURE Y CRUCES BLINDADOS)
# =====================================================
class Partido(models.Model):
    ESTADOS = [
        ('PROG', 'Programado'), 
        ('VIVO', 'En Vivo (Arbitrando)'), 
        ('ACTA', 'En Acta (Faltan Firmas)'), 
        ('JUG', 'Finalizado'), 
        ('WO', 'Walkover')
    ]
    # ✨ AGREGAMOS 'TERC' PARA EL TERCER LUGAR
    ETAPAS = [
        ('F1', 'Fase 1'), ('F2', 'Fase 2'), 
        ('4TOS', 'Cuartos'), ('SEMI', 'Semifinal'), 
        ('TERC', 'Tercer Lugar'), ('FINAL', 'Final')
    ]
    
    informe_vocal = models.TextField(blank=True, null=True)
    informe_arbitro = models.TextField(blank=True, null=True)
    validado_local = models.BooleanField(default=False)
    validado_visita = models.BooleanField(default=False)

    numero_fecha = models.PositiveIntegerField(default=1)
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE)
    etapa = models.CharField(max_length=5, choices=ETAPAS, default='F1')
    cancha = models.CharField(max_length=100, default="Cancha Principal")
    
    equipo_local = models.ForeignKey(Equipo, related_name='local', on_delete=models.CASCADE)
    equipo_visita = models.ForeignKey(Equipo, related_name='visita', on_delete=models.CASCADE)
    
    fecha_hora = models.DateTimeField(null=True, blank=True)
    
    goles_local = models.PositiveIntegerField(default=0)
    goles_visita = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=4, choices=ESTADOS, default='PROG')
    ganador_wo = models.ForeignKey(Equipo, null=True, blank=True, on_delete=models.SET_NULL)

    # ✨ NUEVOS CAMPOS PARA PENALES
    hubo_penales = models.BooleanField(default=False, verbose_name="¿Hubo Penales?")
    penales_local = models.PositiveIntegerField(default=0, blank=True, null=True)
    penales_visita = models.PositiveIntegerField(default=0, blank=True, null=True)

    def clean(self):
        if self.equipo_local == self.equipo_visita:
            raise ValidationError("⛔ Un equipo no puede jugar contra sí mismo.")

        choque = Partido.objects.filter(
            torneo=self.torneo,
            etapa=self.etapa,
        ).filter(
            Q(equipo_local=self.equipo_local, equipo_visita=self.equipo_visita) |
            Q(equipo_local=self.equipo_visita, equipo_visita=self.equipo_local)
        ).exclude(id=self.id)

        if choque.exists():
            raise ValidationError(f"⛔ El partido {self.equipo_local} vs {self.equipo_visita} YA EXISTE en la {self.get_etapa_display()}. No se pueden enfrentar 2 veces en la misma fase.")

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visita}"

# =====================================================
# 8. DETALLE DEL PARTIDO Y SANCIONES
# =====================================================
class DetallePartido(models.Model):
    TIPOS = [
        ('GOL', '⚽ Gol'), ('ASIS', '✅ Asistencia'), ('TA', '🟨 Amarilla'),
        ('TR', '🟥 Roja'), ('DA', '🟨🟨 Doble A.'), ('AZUL', '👕 Uniforme'), ('EBRI', '🍺 Ebrio')
    ]
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name='detalles')
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=5, choices=TIPOS)
    minuto = models.PositiveIntegerField(blank=True, null=True, default=0) 
    observacion = models.TextField(blank=True, null=True)

class Sancion(models.Model):
    TIPOS = [
        ('INSCRIPCION', 'Deuda por Inscripción'),
        ('AMARILLA', 'Tarjeta Amarilla'), 
        ('ROJA', 'Tarjeta Roja'), 
        ('ADMIN', 'Sanción Administrativa')
    ]
    
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE)
    equipo = models.ForeignKey('Equipo', on_delete=models.CASCADE, related_name='sanciones')
    jugador = models.ForeignKey('Jugador', on_delete=models.SET_NULL, null=True, blank=True)
    partido = models.ForeignKey('Partido', on_delete=models.SET_NULL, null=True, blank=True)
    
    tipo = models.CharField(max_length=15, choices=TIPOS)
    monto = models.DecimalField(max_digits=5, decimal_places=2)
    descripcion = models.CharField(max_length=200, blank=True)
    
    pagada = models.BooleanField(default=False, verbose_name="¿Pagada?")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    monto_pagado = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    def __str__(self):
        estado = "PAGADO" if self.pagada else "DEUDA"
        return f"{self.equipo.nombre} - {self.get_tipo_display()} (${self.monto}) [{estado}]"
    
    @property
    def saldo(self):
        return self.monto - self.monto_pagado

# =====================================================
# 9. RESERVA DE CANCHA
# =====================================================

#prueba1
class ReservaCancha(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservas', null=True, blank=True)
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    
    precio_total = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    pagado = models.BooleanField(default=False)
    
    es_torneo = models.BooleanField(default=False, verbose_name="Bloqueo por Torneo")
    motivo_bloqueo = models.CharField(max_length=100, blank=True, null=True)
    
    cupon = models.ForeignKey(Cupon, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    partido = models.OneToOneField('Partido', on_delete=models.CASCADE, null=True, blank=True, related_name='reserva_bloqueo')

    ESTADOS = [
        ('PENDIENTE', '⏳ Pendiente'),
        ('ACTIVA', '✅ Confirmada'),
        ('CANCELADA', '🚫 Cancelada'),
    ]
    estado = models.CharField(max_length=15, choices=ESTADOS, default='PENDIENTE')

    def clean(self):
        APERTURA = time(15, 0)
        CIERRE = time(21, 0)

        if self.hora_inicio < APERTURA or self.hora_fin > CIERRE:
            raise ValidationError("⚠️ La cancha opera de 03:00 PM a 09:00 PM.")
        if self.hora_inicio >= self.hora_fin:
            raise ValidationError("⚠️ Hora inicio debe ser menor a hora fin.")
        if self.hora_inicio.minute != 0 or self.hora_fin.minute != 0:
             raise ValidationError("⚠️ Solo se permiten reservas en horas exactas (ej: 15:00, 16:00).")

        if not self.es_torneo:
            if self.fecha <= timezone.now().date():
                raise ValidationError("⚠️ Solo se aceptan reservas con al menos 1 día de anticipación.")

        choque = ReservaCancha.objects.filter(
            fecha=self.fecha,
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio
        ).exclude(id=self.id).exclude(estado='CANCELADA')

        if choque.exists():
            c = choque.first()
            msg = "⛔ Reservado para CAMPEONATO" if c.es_torneo else "⛔ Ya reservado por otro cliente"
            raise ValidationError(msg)

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if self.precio_total is None:
            self.precio_total = Decimal('0.00')
            
        if not self.es_torneo:
            formato = "%H:%M:%S"
            ini = datetime.strptime(str(self.hora_inicio), formato)
            fin = datetime.strptime(str(self.hora_fin), formato)
            horas = (fin - ini).seconds / 3600
            
            base = float(horas) * 5.00
            if self.cupon and self.cupon.es_valido():
                total = max(0, base - float(self.cupon.descuento))
                if not self.pk:
                    self.cupon.usos_actuales += 1
                    self.cupon.save()
            else:
                total = base
            self.precio_total = Decimal(str(total))
        else:
            self.precio_total = Decimal('0.00')
            
        super().save(*args, **kwargs)

    def __str__(self):
        tipo = "TORNEO" if self.es_torneo else "CLIENTE"
        return f"{self.fecha} | {self.hora_inicio}-{self.hora_fin} ({tipo})"

# =====================================================
# 10. CONFIGURACIÓN GLOBAL
# =====================================================
class Configuracion(models.Model):
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    precio_hora_cancha = models.DecimalField(max_digits=6, decimal_places=2, default=15.00)

    def __str__(self):
        return f"Configuración del Sistema (IVA: {self.iva_porcentaje}%)"

    class Meta:
        verbose_name = "Configuración"
        verbose_name_plural = "Configuraciones"

class HorarioCancha(models.Model):
    hora_inicio = models.TimeField(verbose_name="Hora de Inicio")
    hora_fin = models.TimeField(verbose_name="Hora de Fin")
    precio = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Costo por Hora")
    activo = models.BooleanField(default=True, verbose_name="Disponible para alquilar")

    class Meta:
        verbose_name = "Horario de Cancha"
        verbose_name_plural = "Horarios de Cancha"
        ordering = ['hora_inicio']

    def __str__(self):
        return f"{self.hora_inicio.strftime('%H:%M')} a {self.hora_fin.strftime('%H:%M')} - ${self.precio}"
    
class FotoGaleria(models.Model):
    imagen = models.ImageField(upload_to='galeria/', verbose_name="Foto de la Cancha")
    titulo = models.CharField(max_length=50, blank=True, verbose_name="Título corto (Opcional)")
    orden = models.PositiveIntegerField(default=0, verbose_name="Orden de aparición")
    activa = models.BooleanField(default=True, verbose_name="Mostrar en el inicio")

    class Meta:
        verbose_name = "Foto de Galería"
        verbose_name_plural = "Galería de la Cancha"
        ordering = ['orden', '-id']

    def __str__(self):
        return self.titulo if self.titulo else f"Foto {self.id}"

class Publicidad(models.Model):
    imagen = models.ImageField(upload_to='publicidad/', verbose_name="Banner Publicitario")
    empresa = models.CharField(max_length=100, verbose_name="Nombre de la Empresa o Negocio")
    enlace = models.URLField(blank=True, null=True, verbose_name="Link de WhatsApp o Red Social (Opcional)")
    activa = models.BooleanField(default=True, verbose_name="Mostrar anuncio")

    class Meta:
        verbose_name = "Publicidad"
        verbose_name_plural = "Publicidades"

    def __str__(self):
        return f"Publicidad: {self.empresa}"

class AbonoSancion(models.Model):
    sancion = models.ForeignKey(Sancion, on_delete=models.CASCADE, related_name='historial_abonos')
    monto = models.DecimalField(max_digits=8, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Abono ${self.monto} - {self.sancion.equipo.nombre}"