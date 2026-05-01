from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q, Count, F, Case, When, IntegerField
from django.template.loader import get_template
from django.db import transaction 
from xhtml2pdf import pisa 
from django.contrib.auth.models import User
from django.utils import timezone  
from datetime import datetime, time, timedelta, date
from django.core.exceptions import ValidationError
from urllib.parse import quote
import urllib.parse
from decimal import Decimal
from django.contrib.auth import login

# Importamos Modelos y Formularios Unificados
from .models import (
    Configuracion, Torneo, Equipo, Jugador, Partido, 
    DetallePartido, Pago, Perfil, Sancion, ReservaCancha, Cupon, HorarioCancha,
    FotoGaleria, Publicidad, AbonoSancion
)
from .forms import (
    RegistroUsuarioForm, TorneoForm, EquipoForm, JugadorForm, 
    ProgramarPartidoForm, PagoForm, RegistroPublicoForm,
    ReservaCanchaForm, EquipoSolicitudForm, HorarioCanchaForm,
    FotoGaleriaForm, PublicidadForm
)
from .utils import validar_cedula_ecuador, consultar_sri

# =========================================================
# --- FUNCIONES DE CONTROL DE ACCESO (PERMISOS) ---
# =========================================================

def es_organizador(user):
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol == 'ORG'

def es_vocal_o_admin(user):
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol in ['ORG', 'VOC']

def es_dirigente_o_admin(user):
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol in ['ORG', 'DIR']

# =========================================================
# 1. VISTAS GENERALES Y DE GESTIÓN (CRUD)
# =========================================================

@login_required
def dashboard(request):
    ctx = {}
    ahora = timezone.now()
    
    ctx['torneos'] = Torneo.objects.filter(activo=True).order_by('-id')
    torneo_id = request.GET.get('torneo')
    if torneo_id:
        ctx['torneo_actual'] = int(torneo_id)
        
    partidos_qs = Partido.objects.filter(
        estado='PROG',
        fecha_hora__gte=ahora
    ).select_related('equipo_local', 'equipo_visita', 'torneo').order_by('fecha_hora')[:10]

    for p in partidos_qs:
        p.fecha_local = timezone.localtime(p.fecha_hora).date()
        
    ctx['proximos_partidos'] = partidos_qs

    ctx['fotos_galeria'] = FotoGaleria.objects.filter(activa=True).order_by('orden', '-id')
    ctx['publicidades'] = Publicidad.objects.filter(activa=True).order_by('-id')

    if request.user.is_authenticated and hasattr(request.user, 'perfil'):
        rol = request.user.perfil.rol

        if rol == 'ORG':
            deudas_pendientes = Sancion.objects.filter(pagada=False).exclude(descripcion__icontains='Inscripci').select_related('equipo', 'torneo', 'partido', 'jugador').order_by('-partido__fecha_hora', '-id')
            total = deudas_pendientes.aggregate(Sum('monto'))['monto__sum'] or 0
            
            inscripciones_pendientes = Sancion.objects.filter(pagada=False, descripcion__icontains='Inscripci').aggregate(Sum('monto'))['monto__sum'] or 0
            abonos_inscripciones = Sancion.objects.filter(pagada=False, descripcion__icontains='Inscripci').aggregate(Sum('monto_pagado'))['monto_pagado__sum'] or 0
            saldo_inscripciones = inscripciones_pendientes - abonos_inscripciones
            
            reservas_pendientes = ReservaCancha.objects.filter(estado='PENDIENTE').select_related('usuario').order_by('fecha', 'hora_inicio')
            
            ctx['deudas'] = deudas_pendientes
            ctx['total_por_cobrar'] = total + saldo_inscripciones 
            ctx['reservas_pendientes'] = reservas_pendientes 

        elif rol == 'DIR':
            mis_equipos = Equipo.objects.filter(dirigente=request.user)
            if mis_equipos.exists():
                ctx['mi_equipo'] = mis_equipos.first() 
                mis_deudas = Sancion.objects.filter(equipo__in=mis_equipos, pagada=False).exclude(descripcion__icontains='Inscripci').select_related('partido', 'jugador').order_by('-partido__fecha_hora', '-id')
                
                if mis_deudas.exists():
                    total_deuda = mis_deudas.aggregate(Sum('monto'))['monto__sum'] or 0
                    ctx['tengo_deudas'] = True
                    ctx['monto_deuda'] = total_deuda
                    ctx['lista_mis_deudas'] = mis_deudas
            else:
                ctx['mi_equipo'] = None

        elif rol == 'VOC':
            partidos_pendientes = Partido.objects.filter(
                estado__in=['PROG', 'VIVO']
            ).select_related('equipo_local', 'equipo_visita', 'torneo').order_by('fecha_hora')[:10]
            
            actas_pendientes = Partido.objects.filter(
                estado='ACTA'
            ).select_related('equipo_local', 'equipo_visita', 'torneo').order_by('fecha_hora')[:10]
            
            ctx['partidos_vocal'] = partidos_pendientes
            ctx['actas_pendientes'] = actas_pendientes

    return render(request, 'core/dashboard.html', ctx)

@login_required
@user_passes_test(es_organizador)
def crear_usuario(request):
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            u = form.save()
            u.perfil.rol = form.cleaned_data['rol']
            u.perfil.save()
            messages.success(request, f'Usuario "{u.username}" creado.')
            return redirect('dashboard')
    else:
        form = RegistroUsuarioForm()
    return render(request, 'core/crear_usuario.html', {'form': form})

@login_required
@user_passes_test(es_organizador)
def gestionar_usuarios(request):
    perfiles = Perfil.objects.all().exclude(usuario=request.user).select_related('usuario').order_by('-id')
    if request.method == 'POST':
        perfil_id = request.POST.get('perfil_id')
        nuevo_rol = request.POST.get('nuevo_rol')
        if perfil_id and nuevo_rol:
            p = Perfil.objects.get(id=perfil_id)
            p.rol = nuevo_rol
            p.save()
            messages.success(request, f'Rol de {p.usuario.username} actualizado a {p.get_rol_display()}')
            return redirect('gestionar_usuarios')
    return render(request, 'core/gestionar_usuarios.html', {'perfiles': perfiles})

@login_required
@user_passes_test(es_organizador)
def gestionar_torneos(request):
    torneos = Torneo.objects.all().order_by('-id') 
    if request.method == 'POST':
        form = TorneoForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.organizador = request.user
            t.save()
            messages.success(request, f'✅ Torneo "{t.nombre}" creado exitosamente.')
            return redirect('gestionar_torneos')
        else:
            for campo, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"❌ Error en {campo}: {error}")
    else:
        form = TorneoForm()
    return render(request, 'core/gestionar_torneos.html', {'form': form, 'torneos': torneos})

@login_required
@user_passes_test(es_organizador)
def editar_torneo(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if request.method == 'POST':
        form = TorneoForm(request.POST, instance=torneo)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Torneo "{torneo.nombre}" actualizado correctamente.')
            return redirect('gestionar_torneos')
        else:
            for campo, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"❌ Error en {campo}: {error}")
    else:
        form = TorneoForm(instance=torneo)
    return render(request, 'core/gestionar_torneos.html', {
        'form': form, 'torneos': Torneo.objects.all().order_by('-id'), 'editando': True, 'torneo_edit': torneo
    })

@login_required
@user_passes_test(es_organizador)
def eliminar_torneo(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    nombre_torneo = torneo.nombre
    torneo.delete()
    messages.success(request, f'🗑️ El torneo "{nombre_torneo}" ha sido eliminado completamente.')
    return redirect('gestionar_torneos')

@login_required
@user_passes_test(es_organizador)
def gestionar_equipos(request):
    equipos = Equipo.objects.all().select_related('torneo', 'dirigente')
    if request.method == 'POST':
        form = EquipoForm(request.POST, request.FILES)
        if form.is_valid():
            nuevo_equipo = form.save()
            costo_inscripcion = getattr(nuevo_equipo.torneo, 'precio_inscripcion', Decimal('50.00')) 
            Sancion.objects.create(
                torneo=nuevo_equipo.torneo,
                equipo=nuevo_equipo,
                tipo='ADMIN',
                monto=costo_inscripcion,
                monto_pagado=Decimal('0.00'),
                descripcion=f"Inscripción al Torneo {nuevo_equipo.torneo.nombre}",
                pagada=False
            )
            messages.success(request, '¡Equipo inscrito y cuenta de inscripción generada!')
            return redirect('gestionar_equipos')
    else:
        form = EquipoForm()
    return render(request, 'core/gestionar_equipos.html', {'form': form, 'equipos': equipos})

@login_required
@user_passes_test(es_organizador)
def editar_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    if request.method == 'POST':
        form = EquipoForm(request.POST, request.FILES, instance=equipo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipo actualizado correctamente.')
            return redirect('gestionar_equipos')
    else:
        form = EquipoForm(instance=equipo)
    return render(request, 'core/gestionar_equipos.html', {'form': form, 'equipos': Equipo.objects.all(), 'editando': True})

@login_required
@user_passes_test(es_organizador)
def eliminar_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    equipo.delete()
    messages.success(request, 'Equipo eliminado.')
    return redirect('gestionar_equipos')

@login_required
def gestionar_jugadores(request):
    perfil = request.user.perfil
    puede_fichar = True 
    
    if perfil.rol == 'DIR':
        mis_equipos = Equipo.objects.filter(dirigente=request.user)
        if not mis_equipos.exists():
            messages.error(request, 'No tienes un equipo inscrito. Inscríbete a un torneo primero.')
            return redirect('ver_torneos_activos')

        equipo_id = request.GET.get('equipo')
        if equipo_id:
            mi_equipo = mis_equipos.filter(id=equipo_id).first()
            if not mi_equipo:
                mi_equipo = mis_equipos.first()
        else:
            mi_equipo = mis_equipos.first() 

        jugadores = Jugador.objects.filter(equipo=mi_equipo).order_by('dorsal')
        equipos = mis_equipos
        equipo_seleccionado = mi_equipo.id
        puede_fichar = mi_equipo.puede_fichar 
        
        if request.method == 'POST':
            if not puede_fichar:
                messages.error(request, '⛔ Fichajes cerrados. El organizador no ha habilitado la inscripción para tu equipo.')
                return redirect('gestionar_jugadores')
                
            form = JugadorForm(request.POST, request.FILES)
            form.fields['equipo'].queryset = mis_equipos 
            
            if form.is_valid():
                jugador = form.save(commit=False)
                # MAGIA DE REFUERZOS AUTOMÁTICOS
                fase2_iniciada = Partido.objects.filter(
                    torneo=jugador.equipo.torneo, 
                    etapa__in=['F2', '4TOS', 'SEMI', 'TERC', 'FINAL']
                ).exists()
                if fase2_iniciada:
                    jugador.es_refuerzo = True
                jugador.save()
                
                etiqueta = "(COMO REFUERZO) ⚡" if jugador.es_refuerzo else ""
                messages.success(request, f'¡{jugador.nombres} fichado en {jugador.equipo.nombre} {etiqueta}!')
                return redirect(f"{request.path}?equipo={jugador.equipo.id}")
            else:
                for campo, errores in form.errors.items():
                    for error in errores:
                        messages.error(request, f"❌ Error: {error}")
        else:
            form = JugadorForm(initial={'equipo': mi_equipo})
            form.fields['equipo'].queryset = mis_equipos 

    elif perfil.rol == 'ORG':
        equipos = Equipo.objects.all()
        equipo_id = request.GET.get('equipo')
        if equipo_id:
            jugadores = Jugador.objects.filter(equipo_id=equipo_id).order_by('dorsal')
            equipo_seleccionado = int(equipo_id)
        else:
            jugadores = Jugador.objects.none()
            equipo_seleccionado = None
            
        if request.method == 'POST':
            form = JugadorForm(request.POST, request.FILES)
            if form.is_valid():
                nuevo_jugador = form.save(commit=False)
                # MAGIA DE REFUERZOS AUTOMÁTICOS
                fase2_iniciada = Partido.objects.filter(
                    torneo=nuevo_jugador.equipo.torneo, 
                    etapa__in=['F2', '4TOS', 'SEMI', 'TERC', 'FINAL']
                ).exists()
                if fase2_iniciada:
                    nuevo_jugador.es_refuerzo = True
                nuevo_jugador.save()
                
                etiqueta = "como REFUERZO " if nuevo_jugador.es_refuerzo else ""
                messages.success(request, f'Jugador {nuevo_jugador.nombres} registrado {etiqueta}por Administración.')
                return redirect(f"{request.path}?equipo={form.cleaned_data['equipo'].id}")
            else:
                for campo, errores in form.errors.items():
                    for error in errores:
                        messages.error(request, f"❌ Error: {error}")
        else:
            form = JugadorForm()
    else:
        messages.error(request, "Acceso denegado.")
        return redirect('dashboard')

    return render(request, 'core/gestionar_jugadores.html', {
        'form': form, 'jugadores': jugadores, 'equipos': equipos,
        'equipo_seleccionado': equipo_seleccionado, 'es_dirigente': (perfil.rol == 'DIR'),
        'puede_fichar': puede_fichar 
    })

@login_required
@user_passes_test(es_organizador)
def editar_jugador(request, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id)
    if request.method == 'POST':
        form = JugadorForm(request.POST, request.FILES, instance=jugador)
        if form.is_valid():
            form.save()
            messages.success(request, 'Jugador actualizado.')
            return redirect(f"/jugadores/?equipo={jugador.equipo.id}")
    else:
        form = JugadorForm(instance=jugador)
    return render(request, 'core/gestionar_jugadores.html', {
        'form': form, 'jugadores': Jugador.objects.filter(equipo=jugador.equipo), 
        'equipos': Equipo.objects.all(), 'editando': True
    })

@login_required
def eliminar_jugador(request, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id)
    es_admin = request.user.perfil.rol == 'ORG'
    es_dueno = (request.user.perfil.rol == 'DIR' and jugador.equipo.dirigente == request.user)

    if not (es_admin or es_dueno):
        messages.error(request, "No tienes permiso para eliminar a este jugador.")
        return redirect('dashboard')

    if jugador.detallepartido_set.exists():
        messages.error(request, f"No se puede eliminar a {jugador.nombres} porque ya tiene registros en partidos jugados.")
        if es_admin: return redirect('admin_gestion_jugadores')
        else: return redirect('gestionar_jugadores')

    nombre = jugador.nombres
    jugador.delete()
    messages.success(request, f'Jugador "{nombre}" eliminado correctamente.')
    if es_admin: return redirect('admin_gestion_jugadores')
    else: return redirect('gestionar_jugadores')

def api_consultar_cedula(request):
    cedula = request.GET.get('cedula', '')
    if not validar_cedula_ecuador(cedula):
        return JsonResponse({'error': 'Cédula inválida o incorrecta.'}, status=400)
    
    nombre = consultar_sri(cedula)
    if nombre: return JsonResponse({'nombre': nombre, 'exito': True})
    else: return JsonResponse({'exito': False, 'mensaje': 'Cédula válida, sin datos públicos.'})

# =========================================================
# 2. CALENDARIO Y PARTIDOS (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin)
def programar_partidos(request):
    torneos = Torneo.objects.all()
    torneo_seleccionado = request.GET.get('torneo')
    
    if torneo_seleccionado:
        partidos = Partido.objects.filter(torneo_id=torneo_seleccionado)\
            .select_related('equipo_local', 'equipo_visita')\
            .order_by('etapa', 'numero_fecha', 'fecha_hora')
    else:
        partidos = []
    
    if request.method == 'POST' and es_organizador(request.user):
        form = ProgramarPartidoForm(request.POST)
        
        if form.is_valid():
            equipo_local = form.cleaned_data['equipo_local']
            equipo_visita = form.cleaned_data['equipo_visita']
            etapa_seleccionada = form.cleaned_data.get('etapa', 'F1')
            
            if equipo_local == equipo_visita:
                messages.error(request, "⛔ Error: Un equipo no puede jugar contra sí mismo.")
                return redirect(f"{request.path}?torneo={torneo_seleccionado}")

            if etapa_seleccionada == 'F2':
                if not equipo_local.grupo_fase2 or not equipo_visita.grupo_fase2:
                    messages.error(request, "⛔ Error: Para programar en Fase 2, ambos equipos deben tener un grupo asignado.")
                    return redirect(f"{request.path}?torneo={torneo_seleccionado}")
                
                if equipo_local.grupo_fase2 != equipo_visita.grupo_fase2:
                    messages.error(request, f"⛔ Regla de Grupos: No puedes enfrentar a {equipo_local.nombre} (Grupo {equipo_local.grupo_fase2}) contra {equipo_visita.nombre} (Grupo {equipo_visita.grupo_fase2}) en esta fase.")
                    return redirect(f"{request.path}?torneo={torneo_seleccionado}")
            
            if equipo_local.tiene_deudas():
                messages.warning(request, f"Aviso: {equipo_local.nombre} tiene una deuda pendiente de ${equipo_local.total_deuda()}.")
            if equipo_visita.tiene_deudas():
                messages.warning(request, f"Aviso: {equipo_visita.nombre} tiene una deuda pendiente de ${equipo_visita.total_deuda()}.")
            
            try:
                with transaction.atomic():
                    partido = form.save()
                    duracion = 2 
                    hora_fin_estimada = (partido.fecha_hora + timedelta(hours=duracion)).time()
                    
                    ReservaCancha.objects.create(
                        fecha=partido.fecha_hora.date(),
                        hora_inicio=partido.fecha_hora.time(),
                        hora_fin=hora_fin_estimada,
                        es_torneo=True,
                        motivo_bloqueo=f"⚽ {partido.equipo_local} vs {partido.equipo_visita}",
                        partido=partido,
                        usuario=request.user,
                        estado='ACTIVA',
                        pagado=True
                    )

                messages.success(request, '✅ Partido agendado correctamente en el calendario.')
                return redirect(f"{request.path}?torneo={form.cleaned_data['torneo'].id}")
            
            except ValidationError as e:
                messages.error(request, '⛔ La cancha ya está reservada en ese horario por un cliente externo.')
            except Exception as e:
                messages.error(request, f'Error al agendar: {str(e)}')
        else:
            messages.error(request, "Error en el formulario. Verifica los datos ingresados.")
            
    else:
        form = ProgramarPartidoForm(initial={'torneo': torneo_seleccionado})
        if torneo_seleccionado:
            equipos_aprobados = Equipo.objects.filter(torneo_id=torneo_seleccionado, estado_inscripcion='APROBADO')
            if 'equipo_local' in form.fields:
                form.fields['equipo_local'].queryset = equipos_aprobados
            if 'equipo_visita' in form.fields:
                form.fields['equipo_visita'].queryset = equipos_aprobados

    return render(request, 'core/programar_partidos.html', {
        'partidos': partidos, 'form': form, 'torneos': torneos,
        'torneo_actual': int(torneo_seleccionado) if torneo_seleccionado else None
    })

@login_required
@user_passes_test(es_organizador)
def editar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    if request.method == 'POST':
        form = ProgramarPartidoForm(request.POST, instance=partido)
        if form.is_valid():
            form.save()
            messages.success(request, 'Datos del partido actualizados.')
            return redirect(f"/programar/?torneo={partido.torneo.id}")
    else:
        form = ProgramarPartidoForm(instance=partido)
    return render(request, 'core/editar_partido.html', {'form': form, 'partido': partido})

@login_required
@user_passes_test(es_organizador)
def eliminar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    torneo_id = partido.torneo.id
    partido.delete()
    messages.warning(request, 'Partido eliminado del calendario.')
    return redirect(f"/programar/?torneo={torneo_id}")

@login_required
@user_passes_test(es_organizador)
def reiniciar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    partido.detalles.all().delete()
    Sancion.objects.filter(partido=partido).delete() 
    
    partido.goles_local = 0
    partido.goles_visita = 0
    partido.estado = 'PROG'
    partido.informe_vocal = ""
    partido.informe_arbitro = ""
    partido.validado_local = False
    partido.validado_visita = False
    partido.hubo_penales = False
    partido.penales_local = 0
    partido.penales_visita = 0
    partido.save()
    
    messages.info(request, 'El partido ha sido reiniciado. Ahora está pendiente de juego.')
    return redirect(f"/programar/?torneo={partido.torneo.id}")

# =========================================================
# 3. JUEGO, VOCALÍA Y RESULTADOS (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin)
def registrar_resultado(request, partido_id):
    partido = Partido.objects.get(id=partido_id)
    if request.method == 'POST':
        goles_local = request.POST.get('goles_local')
        goles_visita = request.POST.get('goles_visita')
        wo = request.POST.get('wo')

        if wo == 'on':
            partido.estado = 'WO'
            partido.goles_local = 3
            partido.goles_visita = 0
        else:
            partido.goles_local = int(goles_local)
            partido.goles_visita = int(goles_visita)
            partido.estado = 'JUG' 

        partido.save()
        messages.success(request, f'Resultado registrado: {partido.equipo_local} ({partido.goles_local}) - ({partido.goles_visita}) {partido.equipo_visita}')
        return redirect(f"/programar/?torneo={partido.torneo.id}")
    return render(request, 'core/registrar_resultado.html', {'partido': partido})

@login_required
@user_passes_test(es_vocal_o_admin)
def gestionar_vocalia(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    
    # RESUMEN FINANCIERO DE AMBOS EQUIPOS
    deudas_local = Sancion.objects.filter(equipo=partido.equipo_local, pagada=False).order_by('fecha_creacion')
    deudas_visita = Sancion.objects.filter(equipo=partido.equipo_visita, pagada=False).order_by('fecha_creacion')

    resumen_local = {
        'deuda': partido.equipo_local.total_deuda(),
        'amarillas_equipo': Sancion.objects.filter(equipo=partido.equipo_local, tipo='AMARILLA', pagada=False).count(),
        'rojas_equipo': Sancion.objects.filter(equipo=partido.equipo_local, tipo='ROJA', pagada=False).count(),
    }
    resumen_visita = {
        'deuda': partido.equipo_visita.total_deuda(),
        'amarillas_equipo': Sancion.objects.filter(equipo=partido.equipo_visita, tipo='AMARILLA', pagada=False).count(),
        'rojas_equipo': Sancion.objects.filter(equipo=partido.equipo_visita, tipo='ROJA', pagada=False).count(),
    }

    jugadores_local = Jugador.objects.filter(equipo=partido.equipo_local).annotate(
        goles_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='GOL')),
        ta_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='TA')),
        tr_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='TR')),
        da_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='DA')) 
    ).order_by('dorsal')

    jugadores_visita = Jugador.objects.filter(equipo=partido.equipo_visita).annotate(
        goles_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='GOL')),
        ta_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='TA')),
        tr_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='TR')),
        da_match=Count('detallepartido', filter=Q(detallepartido__partido=partido, detallepartido__tipo='DA'))
    ).order_by('dorsal')

    for j in jugadores_local:
        j.mis_eventos = DetallePartido.objects.filter(partido=partido, jugador=j).only('id', 'tipo')
    for j in jugadores_visita:
        j.mis_eventos = DetallePartido.objects.filter(partido=partido, jugador=j).only('id', 'tipo')

    asistencias_ids = list(DetallePartido.objects.filter(partido=partido, tipo='ASIS').values_list('jugador_id', flat=True))
    multas = Sancion.objects.filter(partido=partido).order_by('-id')

    if request.method == 'POST':
        if 'guardar_informe' in request.POST:
            estado_anterior = partido.estado

            partido.informe_vocal = request.POST.get('informe_vocal')
            partido.informe_arbitro = request.POST.get('informe_arbitro')
            partido.validado_local = request.POST.get('validado_local') == 'on'
            partido.validado_visita = request.POST.get('validado_visita') == 'on'
            
            if partido.etapa in ['4TOS', 'SEMI', 'TERC', 'FINAL']:
                p_local = request.POST.get('penales_local', 0)
                p_visita = request.POST.get('penales_visita', 0)
                p_local = int(p_local) if p_local else 0
                p_visita = int(p_visita) if p_visita else 0
                if p_local > 0 or p_visita > 0:
                    partido.hubo_penales = True
                    partido.penales_local = p_local
                    partido.penales_visita = p_visita
                else:
                    partido.hubo_penales = False
                    partido.penales_local = 0
                    partido.penales_visita = 0

            if partido.validado_local and partido.validado_visita:
                partido.estado = 'JUG'
            else:
                partido.estado = 'ACTA'
            
            partido.save()

            if estado_anterior in ['PROG', 'VIVO', 'ACTA'] and partido.estado == 'JUG':
                
                jugadores_ambos_equipos = Jugador.objects.filter(equipo__in=[partido.equipo_local, partido.equipo_visita], partidos_suspension__gt=0)
                detalles = DetallePartido.objects.filter(partido=partido)
                
                for j in jugadores_ambos_equipos:
                    if not detalles.filter(jugador=j, tipo__in=['DA', 'TR']).exists():
                        j.partidos_suspension -= 1
                        j.save()

                jugadores_con_eventos = set([d.jugador for d in detalles])
                for j in jugadores_con_eventos:
                    eventos_j = detalles.filter(jugador=j)
                    ta_partido = eventos_j.filter(tipo='TA').count()
                    da_partido = eventos_j.filter(tipo='DA').count()
                    tr_partido = eventos_j.filter(tipo='TR').count()

                    if tr_partido > 0:
                        j.partidos_suspension += 2
                        j.save()
                        Sancion.objects.create(torneo=partido.torneo, equipo=j.equipo, jugador=j, partido=partido, tipo='ROJA', monto=partido.torneo.costo_roja, descripcion=f"Roja Directa - {j.nombres}")
                    
                    if da_partido > 0:
                        j.partidos_suspension += 1
                        j.save()
                        Sancion.objects.create(torneo=partido.torneo, equipo=j.equipo, jugador=j, partido=partido, tipo='ROJA', monto=partido.torneo.costo_roja, descripcion=f"Roja por Acumulación - {j.nombres}")
                    
                    if ta_partido > 0:
                        Sancion.objects.create(torneo=partido.torneo, equipo=j.equipo, jugador=j, partido=partido, tipo='AMARILLA', monto=partido.torneo.costo_amarilla, descripcion=f"Tarjeta Amarilla - {j.nombres}")
                        
                        # ✨ NUEVA REGLA DE AMARILLAS POR ETAPA ✨
                        if partido.etapa == 'F1':
                            limite_ta = 4
                            fases_validas = ['F1']
                        elif partido.etapa == 'F2':
                            limite_ta = 3
                            fases_validas = ['F2']
                        else:
                            limite_ta = 2
                            fases_validas = ['4TOS', 'SEMI', 'TERC', 'FINAL']
                        
                        total_ta_fase = DetallePartido.objects.filter(
                            jugador=j, 
                            partido__torneo=partido.torneo, 
                            partido__etapa__in=fases_validas,
                            tipo='TA'
                        ).count()
                        
                        if total_ta_fase > 0 and total_ta_fase % limite_ta == 0:
                            j.partidos_suspension += 1
                            j.save()

                messages.success(request, '✅ Acta firmada por ambos equipos. Partido Finalizado y Sanciones aplicadas.')
                return redirect(f"/programar/?torneo={partido.torneo.id}")
            
            else:
                if 'guardar_y_volver' in request.POST:
                    messages.info(request, '📋 Partido guardado en Actas. (Aún faltan firmas para cerrarlo).')
                    return redirect(f"/programar/?torneo={partido.torneo.id}")
                else:
                    messages.warning(request, '⚠️ Faltan las firmas de ambos equipos para Finalizar el partido oficialmente.')
                    return redirect('gestionar_vocalia', partido_id=partido_id)
        
        elif 'nueva_multa' in request.POST:
            equipo_id = request.POST.get('equipo_multa')
            motivo = request.POST.get('motivo_multa')
            monto = request.POST.get('monto_multa')
            if equipo_id and motivo and monto:
                Sancion.objects.create(
                    torneo=partido.torneo, equipo_id=equipo_id, partido=partido,
                    tipo='ADMIN', monto=monto, descripcion=motivo, pagada=False
                )
            return redirect('gestionar_vocalia', partido_id=partido_id)

    return render(request, 'core/gestionar_vocalia.html', {
        'partido': partido,
        'resumen_local': resumen_local,
        'resumen_visita': resumen_visita,
        'deudas_local': deudas_local,  # <- Agregar esto
        'deudas_visita': deudas_visita,
        'jugadores_local': jugadores_local,
        'jugadores_visita': jugadores_visita,
        'asistencias_ids': asistencias_ids,
        'multas': multas
    })

@login_required
@user_passes_test(es_vocal_o_admin)
def registrar_incidencia(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    
    if request.user.perfil.rol not in ['VOC', 'ORG']:
        messages.error(request, "No tienes permiso para realizar esta acción.")
        return redirect('dashboard')

    if request.method == 'POST':
        jugador_id = request.POST.get('jugador_id')
        tipo_evento = request.POST.get('tipo') 
        minuto = request.POST.get('minuto', 0)
        
        jugador = get_object_or_404(Jugador, id=jugador_id)

        if tipo_evento == 'TA':
            amarilla_previa = DetallePartido.objects.filter(partido=partido, jugador=jugador, tipo='TA').first()
            if amarilla_previa:
                amarilla_previa.delete()
                DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='DA', observacion="Roja por Acumulación")
                messages.error(request, f'🟥 ¡ROJA POR ACUMULACIÓN para {jugador.nombres}!')
            else:
                DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='TA', minuto=int(minuto) if minuto else 0)
                messages.warning(request, f'🟨 Tarjeta Amarilla registrada a {jugador.nombres}.')

        elif tipo_evento == 'TR':
            DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='TR', minuto=int(minuto) if minuto else 0)
            messages.error(request, f'🟥 ¡ROJA DIRECTA para {jugador.nombres}!')

        elif tipo_evento == 'GOL':
            DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='GOL', minuto=int(minuto) if minuto else 0)
            if jugador.equipo == partido.equipo_local:
                partido.goles_local += 1
            else:
                partido.goles_visita += 1
            messages.success(request, f'⚽ ¡Gol de {jugador.nombres}!')
        
        if partido.estado == 'PROG':
            partido.estado = 'VIVO'
        
        partido.save()

    return redirect('gestionar_vocalia', partido_id=partido.id)

@login_required
@user_passes_test(es_vocal_o_admin)
def eliminar_evento_ultimo(request, partido_id, jugador_id, tipo):
    if tipo == 'TA':
        evento_da = DetallePartido.objects.filter(partido_id=partido_id, jugador_id=jugador_id, tipo='DA').last()
        if evento_da:
            evento_da.delete()
            DetallePartido.objects.create(partido_id=partido_id, jugador_id=jugador_id, tipo='TA')
            messages.success(request, "Corrección: Roja por Acumulación anulada. Se restauró 1 Amarilla.")
            return redirect('gestionar_vocalia', partido_id=partido_id)

    evento = DetallePartido.objects.filter(
        partido_id=partido_id, 
        jugador_id=jugador_id, 
        tipo=tipo
    ).last()
    
    if evento:
        partido = evento.partido
        if tipo == 'GOL':
            if evento.jugador.equipo == partido.equipo_local:
                partido.goles_local = max(0, partido.goles_local - 1)
            else:
                partido.goles_visita = max(0, partido.goles_visita - 1)
            partido.save()
        
        evento.delete()
        messages.warning(request, f"Corrección: Se eliminó el último registro de {tipo} para {evento.jugador.nombres}.")
    
    return redirect('gestionar_vocalia', partido_id=partido_id)

@login_required
@user_passes_test(es_vocal_o_admin)
def eliminar_evento(request, evento_id):
    evento = DetallePartido.objects.get(id=evento_id)
    partido = evento.partido
    
    if evento.tipo == 'GOL':
        if evento.jugador.equipo == partido.equipo_local:
            partido.goles_local = max(0, partido.goles_local - 1)
        else:
            partido.goles_visita = max(0, partido.goles_visita - 1)
        partido.save()
    
    evento.delete()
    messages.success(request, 'Corrección realizada: Evento eliminado.')
    return redirect('gestionar_vocalia', partido_id=partido.id)


@login_required
@user_passes_test(es_vocal_o_admin)
def eliminar_multa(request, multa_id):
    sancion = get_object_or_404(Sancion, id=multa_id)
    partido_id = sancion.partido.id if sancion.partido else None
    sancion.delete()
    messages.success(request, 'Sanción administrativa eliminada correctamente.')
    
    if partido_id:
        return redirect('gestionar_vocalia', partido_id=partido_id)
    return redirect('dashboard')


@login_required
@user_passes_test(es_vocal_o_admin)
def toggle_asistencia(request, partido_id, jugador_id):
    partido = get_object_or_404(Partido, id=partido_id)
    jugador = get_object_or_404(Jugador, id=jugador_id)
    
    asistencia = DetallePartido.objects.filter(partido=partido, jugador=jugador, tipo='ASIS').first()
    
    if asistencia:
        with transaction.atomic():
            goles_jugador = DetallePartido.objects.filter(partido=partido, jugador=jugador, tipo='GOL').count()
            if goles_jugador > 0:
                if jugador.equipo == partido.equipo_local:
                    partido.goles_local = max(0, partido.goles_local - goles_jugador)
                else:
                    partido.goles_visita = max(0, partido.goles_visita - goles_jugador)
                partido.save()
                
            DetallePartido.objects.filter(partido=partido, jugador=jugador).delete()
            messages.warning(request, f'Se retiró a {jugador.nombres}. Historial del partido limpiado.')
    else:
        DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='ASIS')
        messages.success(request, f'{jugador.nombres} ingresó a la cancha.')
        
    return redirect('gestionar_vocalia', partido_id=partido.id)

# =========================================================
# 4. REPORTES Y ESTADÍSTICAS
# =========================================================

@login_required
def tabla_posiciones(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    equipos = Equipo.objects.filter(torneo=torneo, estado_inscripcion='APROBADO')
    
    # Función interna para no repetir código matemático
    def calcular_estadisticas(filtro_vuelta=None):
        tabla = []
        for equipo in equipos:
            # Filtramos los partidos jugados por este equipo en la Fase 1
            partidos_jugados = Partido.objects.filter(
                torneo=torneo, etapa='F1', estado__in=['JUG', 'WO']
            ).filter(Q(equipo_local=equipo) | Q(equipo_visita=equipo))
            
            # Si pedimos solo la segunda vuelta, filtramos
            if filtro_vuelta:
                partidos_jugados = partidos_jugados.filter(vuelta=filtro_vuelta)
                
            pj = pg = pe = pp = gf = gc = 0
            
            for p in partidos_jugados:
                pj += 1
                es_local = (p.equipo_local == equipo)
                goles_favor = p.goles_local if es_local else p.goles_visita
                goles_contra = p.goles_visita if es_local else p.goles_local
                
                gf += goles_favor
                gc += goles_contra
                
                if goles_favor > goles_contra:
                    pg += 1
                elif goles_favor == goles_contra:
                    pe += 1
                else:
                    pp += 1
            
            # Puntos: Partidos Ganados * 3 + Empates * 1 + BONIFICACIÓN
            puntos = (pg * 3) + (pe * 1) + equipo.puntos_bonificacion
            gd = gf - gc
            
            tabla.append({
                'equipo': equipo,
                'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp,
                'gf': gf, 'gc': gc, 'gd': gd,
                'puntos': puntos,
                'bono': equipo.puntos_bonificacion
            })
            
        # Ordenamos por Puntos, luego Gol Diferencia, luego Goles a Favor
        return sorted(tabla, key=lambda x: (x['puntos'], x['gd'], x['gf']), reverse=True)

    # Generamos ambas tablas
    tabla_general = calcular_estadisticas(filtro_vuelta=None) # Suma todo
    tabla_vuelta2 = calcular_estadisticas(filtro_vuelta=2)    # Solo Vuelta 2
    
    # Verificamos si ya existe la segunda vuelta para mostrar o no el botón de generarla
    existe_vuelta2 = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2).exists()

    return render(request, 'core/tabla_posiciones.html', {
        'torneo': torneo,
        'tabla_general': tabla_general,
        'tabla_vuelta2': tabla_vuelta2,
        'existe_vuelta2': existe_vuelta2,
        'es_organizador': request.user.perfil.rol == 'ORG'
    })

@login_required
@user_passes_test(es_organizador)
def generar_fase2(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    equipos = Equipo.objects.filter(torneo=torneo, estado_inscripcion='APROBADO')
    
    ida_y_vuelta = request.POST.get('ida_y_vuelta') == 'on'
    torneo.fase2_ida_vuelta = ida_y_vuelta
    torneo.save()

    tabla = []
    for equipo in equipos:
        partidos = Partido.objects.filter(Q(equipo_local=equipo) | Q(equipo_visita=equipo), estado__in=['JUG', 'WO', 'FINALIZADO'], etapa='F1')
        puntos = 0; gf = 0; gc = 0
        for p in partidos:
            es_local = (p.equipo_local == equipo)
            goles_pro = p.goles_local if es_local else p.goles_visita
            goles_riv = p.goles_visita if es_local else p.goles_local
            gf += goles_pro; gc += goles_riv
            if goles_pro > goles_riv: puntos += 3
            elif goles_pro == goles_riv: puntos += 1
        gd = gf - gc
        tabla.append({'equipo': equipo, 'pts': puntos, 'gd': gd, 'gf': gf})

    tabla_ordenada = sorted(tabla, key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)

    with transaction.atomic():
        for index, fila in enumerate(tabla_ordenada):
            equipo = fila['equipo']
            posicion = index + 1
            equipo.puntos_bonificacion = 0 
            
            if posicion == 1:
                equipo.puntos_bonificacion = 2
            elif posicion == 2:
                equipo.puntos_bonificacion = 1

            if posicion % 2 != 0:
                equipo.grupo_fase2 = 'A'
            else:
                equipo.grupo_fase2 = 'B'
            equipo.save()

    formato_texto = "Ida y Vuelta" if ida_y_vuelta else "Solo Ida"
    messages.success(request, f'✅ Fase 2 generada en formato: {formato_texto}. Equipos divididos y bonos asignados.')
    return redirect('tabla_posiciones_f2', torneo_id=torneo.id)

@login_required
def tabla_posiciones_f2(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    
    def calcular_grupo(letra_grupo):
        equipos_grupo = Equipo.objects.filter(torneo=torneo, grupo_fase2=letra_grupo, estado_inscripcion='APROBADO')
        lista_tabla = []
        
        for equipo in equipos_grupo:
            partidos = Partido.objects.filter(
                Q(equipo_local=equipo) | Q(equipo_visita=equipo),
                estado__in=['JUG', 'WO', 'FINALIZADO'],
                etapa='F2' 
            )
            
            pj=0; pg=0; pe=0; pp=0; gf=0; gc=0
            for p in partidos:
                pj+=1
                es_local = (p.equipo_local == equipo)
                goles_pro = p.goles_local if es_local else p.goles_visita
                goles_rival = p.goles_visita if es_local else p.goles_local
                gf+=goles_pro; gc+=goles_rival
                
                if goles_pro > goles_rival: pg+=1
                elif goles_pro < goles_rival: pp+=1
                else: pe+=1
            
            puntos = (pg * 3) + (pe * 1) + equipo.puntos_bonificacion
            gd = gf - gc
            
            lista_tabla.append({
                'equipo': equipo, 
                'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp,
                'gf': gf, 'gc': gc, 'gd': gd, 
                'pts': puntos,
                'bono': equipo.puntos_bonificacion
            })
        
        return sorted(lista_tabla, key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)

    tabla_a = calcular_grupo('A')
    tabla_b = calcular_grupo('B')
    
    cuartos_generados = Partido.objects.filter(torneo=torneo, etapa='4TOS').exists()
    llaves_ya_generadas = Partido.objects.filter(torneo=torneo, etapa__in=['4TOS', 'SEMI', 'TERC', 'FINAL']).exists()
    
    return render(request, 'core/tabla_posiciones_f2.html', {
        'torneo': torneo, 
        'tabla_a': tabla_a, 
        'tabla_b': tabla_b,
        'llaves_ya_generadas': llaves_ya_generadas,
        'fase': 2,
        'cuartos_generados': cuartos_generados,
        'es_organizador': request.user.perfil.rol == 'ORG'
    })

def seleccionar_reporte(request):
    torneos = Torneo.objects.all().order_by('-activo', '-fecha_inicio')
    return render(request, 'core/seleccionar_reporte.html', {'torneos': torneos})

from django.db.models import Sum, Q

def reporte_estadisticas(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    # 1. Determinar el ROL
    rol = request.user.perfil.rol if request.user.is_authenticated else 'PUB'
    
    # 2. Control Inteligente de Fases
    fase2_generada = Partido.objects.filter(torneo=torneo, etapa='F2').exists()
    hay_llaves = Partido.objects.filter(torneo=torneo, etapa__in=['4TOS', 'SEMI', 'TERC', 'FINAL']).exists()
    
    # 🔥 AQUI SE VERIFICA SI EXISTE LA 2DA VUELTA
    existe_vuelta2 = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2).exists()
    
    if rol == 'ORG':
        fase_actual = int(request.GET.get('fase', 2 if fase2_generada else 1))
    else:
        fase_actual = 2 if fase2_generada else 1

    # 3. Variables Base
    tabla_general = []
    tabla_vuelta2 = []
    tabla_a = []
    tabla_b = []
    
    equipos = Equipo.objects.filter(torneo=torneo)
    equipos_todos = equipos # Solución para el Fair Play
    
    # ==========================================
    # CÁLCULO DE FASE 1
    # ==========================================
    if fase_actual == 1:
        for eq in equipos:
            locales = Partido.objects.filter(torneo=torneo, etapa='F1', equipo_local=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
            visitas = Partido.objects.filter(torneo=torneo, etapa='F1', equipo_visita=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
            
            # --- TABLA GENERAL (Suma TODO y los bonos) ---
            pj=pg=pe=pp=gf=gc=0
            for p in locales:
                pj+=1; gf+=p.goles_local; gc+=p.goles_visita
                if p.goles_local > p.goles_visita: pg+=1
                elif p.goles_local == p.goles_visita: pe+=1
                else: pp+=1
            for p in visitas:
                pj+=1; gf+=p.goles_visita; gc+=p.goles_local
                if p.goles_visita > p.goles_local: pg+=1
                elif p.goles_visita == p.goles_local: pe+=1
                else: pp+=1
            
            pts = (pg * 3) + pe + eq.puntos_bonificacion
            tabla_general.append({
                'equipo': eq, 'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp, 
                'gf': gf, 'gc': gc, 'gd': gf-gc, 'puntos': pts, 'bono': eq.puntos_bonificacion
            })

            # --- TABLA SEGUNDA VUELTA (Exclusiva) ---
            if existe_vuelta2:
                loc2 = locales.filter(vuelta=2)
                vis2 = visitas.filter(vuelta=2)
                pj2=pg2=pe2=pp2=gf2=gc2=0
                for p in loc2:
                    pj2+=1; gf2+=p.goles_local; gc2+=p.goles_visita
                    if p.goles_local > p.goles_visita: pg2+=1
                    elif p.goles_local == p.goles_visita: pe2+=1
                    else: pp2+=1
                for p in vis2:
                    pj2+=1; gf2+=p.goles_visita; gc2+=p.goles_local
                    if p.goles_visita > p.goles_local: pg2+=1
                    elif p.goles_visita == p.goles_local: pe2+=1
                    else: pp2+=1
                
                pts2 = (pg2 * 3) + pe2 + eq.puntos_bonificacion
                tabla_vuelta2.append({
                    'equipo': eq, 'pj': pj2, 'pg': pg2, 'pe': pe2, 'pp': pp2, 
                    'gf': gf2, 'gc': gc2, 'gd': gf2-gc2, 'puntos': pts2, 'bono': eq.puntos_bonificacion
                })

        # Ordenar tablas
        tabla_general.sort(key=lambda x: (x['puntos'], x['gd'], x['gf']), reverse=True)
        if existe_vuelta2:
            tabla_vuelta2.sort(key=lambda x: (x['puntos'], x['gd'], x['gf']), reverse=True)

    # ==========================================
    # CÁLCULO DE FASE 2
    # ==========================================
    elif fase_actual == 2:
        for eq in equipos:
            if not eq.grupo_fase2: continue
            locales = Partido.objects.filter(torneo=torneo, etapa='F2', equipo_local=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
            visitas = Partido.objects.filter(torneo=torneo, etapa='F2', equipo_visita=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
            
            pj=pg=pe=pp=gf=gc=0
            for p in locales:
                pj+=1; gf+=p.goles_local; gc+=p.goles_visita
                if p.goles_local > p.goles_visita: pg+=1
                elif p.goles_local == p.goles_visita: pe+=1
                else: pp+=1
            for p in visitas:
                pj+=1; gf+=p.goles_visita; gc+=p.goles_local
                if p.goles_visita > p.goles_local: pg+=1
                elif p.goles_visita == p.goles_local: pe+=1
                else: pp+=1
            
            pts = (pg * 3) + pe + eq.puntos_bonificacion
            fila = {'equipo': eq, 'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp, 'gf': gf, 'gc': gc, 'gd': gf-gc, 'pts': pts}
            
            if eq.grupo_fase2 == 'A': tabla_a.append(fila)
            elif eq.grupo_fase2 == 'B': tabla_b.append(fila)
            
        tabla_a.sort(key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)
        tabla_b.sort(key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)

    # ==========================================
    # ESTADÍSTICAS EXTRA (Goleadores, Sanciones)
    # ==========================================
    goleadores = DetallePartido.objects.filter(partido__torneo=torneo, tipo='GOL').values(
        'jugador__nombres', 'jugador__equipo__nombre', 'jugador__equipo__escudo'
    ).annotate(total_goles=Count('id')).order_by('-total_goles', 'jugador__nombres')[:15]

    sancionados_activos = Sancion.objects.filter(torneo=torneo, pagada=False).select_related('jugador', 'equipo')
    # Equipos permitidos para dropdown
    if rol == 'DIR':
        equipos_permitidos = equipos_todos.filter(representante=request.user)
    else:
        equipos_permitidos = equipos_todos

    equipo_id = request.GET.get('equipo')
    equipo_seleccionado = None
    jugadores_detalle = []

    if equipo_id:
        equipo_seleccionado = get_object_or_404(Equipo, id=equipo_id, torneo=torneo)
        if rol == 'ORG' or (rol == 'DIR' and equipo_seleccionado.representante == request.user) or rol == 'PUB':
            jugadores = Jugador.objects.filter(equipo=equipo_seleccionado)
            for j in jugadores:
                ta = Tarjeta.objects.filter(jugador=j, partido__torneo=torneo, tipo='AMARILLA').count()
                da = Tarjeta.objects.filter(jugador=j, partido__torneo=torneo, tipo='DOBLE_AMARILLA').count()
                tr = Tarjeta.objects.filter(jugador=j, partido__torneo=torneo, tipo='ROJA').count()
                
                pj_jugador = Partido.objects.filter(torneo=torneo, estado__in=['FINALIZADO', 'JUG']).filter(Q(equipo_local=equipo_seleccionado) | Q(equipo_visita=equipo_seleccionado)).count()
                jugadores_detalle.append({'nombre': j.nombres, 'pj': pj_jugador, 'ta': ta, 'da': da, 'tr': tr})
            jugadores_detalle.sort(key=lambda x: (x['tr'], x['da'], x['ta']), reverse=True)

    return render(request, 'core/reporte_estadisticas.html', {
        'torneo': torneo, 
        'rol': rol,
        'fase_actual': fase_actual,
        'hay_llaves': hay_llaves,
        'tabla_general': tabla_general,
        'tabla_vuelta2': tabla_vuelta2,
        'existe_vuelta2': existe_vuelta2,
        'tabla_a': tabla_a,
        'tabla_b': tabla_b,
        'goleadores': goleadores, 
        'equipos_permitidos': equipos_permitidos, 
        'equipo_seleccionado': equipo_seleccionado, 
        'jugadores_detalle': jugadores_detalle, 
        'sancionados_activos': sancionados_activos, 
    })

@login_required
def tabla_goleadores(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    goleadores = DetallePartido.objects.filter(partido__torneo=torneo, tipo='GOL').values(
        'jugador__nombres', 'jugador__equipo__nombre', 'jugador__equipo__escudo'
    ).annotate(total_goles=Count('id')).order_by('-total_goles', 'jugador__nombres')[:10]
    return render(request, 'core/tabla_goleadores.html', {'torneo': torneo, 'goleadores': goleadores})

# =========================================================
# 5. GENERACIÓN DE PDF (ACTA) (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin)
def generar_acta_pdf(request, partido_id):
    partido = Partido.objects.get(id=partido_id)
    detalles = DetallePartido.objects.filter(partido=partido).select_related('jugador')
    
    asistencias_local = detalles.filter(tipo='ASIS', jugador__equipo=partido.equipo_local)
    asistencias_visita = detalles.filter(tipo='ASIS', jugador__equipo=partido.equipo_visita)
    goles = detalles.filter(tipo='GOL')
    tarjetas = detalles.filter(tipo__in=['TA', 'TR', 'DA', 'AZUL', 'EBRI'])

    template_path = 'core/acta_partido_pdf.html'
    context = {
        'partido': partido,
        'asistencias_local': asistencias_local,
        'asistencias_visita': asistencias_visita,
        'goles': goles,
        'tarjetas': tarjetas,
    }
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Acta_{partido.id}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('Error al generar PDF <pre>' + html + '</pre>')
    return response

# =========================================================
# 6. FINANZAS Y PAGOS
# =========================================================

@login_required
@user_passes_test(es_organizador)
def registrar_pago(request):
    equipo_id = request.GET.get('equipo')
    equipo = get_object_or_404(Equipo, id=equipo_id) if equipo_id else None

    if request.method == 'POST':
        form = PagoForm(request.POST, request.FILES)
        
        if form.is_valid():
            pago = form.save(commit=False)
            if equipo:
                pago.equipo = equipo
                
            pago.save() 
            messages.success(request, f'🤑 Pago de ${pago.monto} registrado para {pago.equipo.nombre}')
            return redirect('gestionar_finanzas')
        else:
            messages.error(request, "Error en el formulario. Revisa los campos.")
            
    else:
        initial_data = {'equipo': equipo} if equipo else {}
        form = PagoForm(initial=initial_data)
        form.fields['equipo'].queryset = Equipo.objects.filter(estado_inscripcion='APROBADO')

    return render(request, 'core/registrar_pago.html', {
        'form': form, 
        'equipo': equipo 
    })


@login_required
@user_passes_test(es_organizador)
def historial_pagos_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    pagos = Pago.objects.filter(equipo=equipo).order_by('-fecha', '-id')
    
    return render(request, 'core/historial_pagos.html', {
        'equipo': equipo,
        'pagos': pagos
    })

def generar_recibo_pago_pdf(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    
    template_path = 'core/acta_pago_pdf.html'
    context = {'pago': pago}
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Recibo_Pago_{pago.id}_{pago.equipo.nombre}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('Error al generar el PDF <pre>' + html + '</pre>')
    return response

# =========================================================
# 7. REGISTRO PÚBLICO Y RESERVAS
# =========================================================

def registro_publico(request):
    if request.method == 'POST':
        # Usamos el nombre correcto de tu formulario
        form = RegistroPublicoForm(request.POST) 
        
        if form.is_valid():
            # Guardamos el nuevo usuario en la base de datos
            usuario = form.save()
            
            # ✨ MAGIA DE AUTO-LOGIN ✨
            login(request, usuario)
            
            # Un mensajito de bienvenida nunca está de más
            messages.success(request, f'¡Bienvenido crack! Tu cuenta ha sido creada y ya estás dentro.')
            
            # Lo mandamos directo al dashboard
            return redirect('dashboard') 
    else:
        # Si recién entra a la página, le mostramos el formulario vacío
        form = RegistroPublicoForm()
        
    return render(request, 'registration/registro_publico.html', {'form': form})

def reservar_cancha(request):
    manana = timezone.now().date() + timedelta(days=1)
    
    fecha_str = request.GET.get('fecha')
    if fecha_str:
        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            if fecha_consulta <= timezone.now().date():
                messages.warning(request, "Recuerda: Solo se puede reservar con al menos 1 día de anticipación.")
                fecha_consulta = manana
        except ValueError:
            fecha_consulta = manana
    else:
        fecha_consulta = manana

    horarios_disponibles = []
    
    horarios_db = HorarioCancha.objects.filter(activo=True).order_by('hora_inicio')
    reservas_del_dia = ReservaCancha.objects.filter(fecha=fecha_consulta).exclude(estado='CANCELADA')
    partidos_del_dia = Partido.objects.filter(fecha_hora__date=fecha_consulta).exclude(estado='WO')

    for tarifa in horarios_db:
        hora_actual = tarifa.hora_inicio
        hora_final = tarifa.hora_fin
        
        while hora_actual < hora_final:
            dummy_date = datetime.today()
            dt_actual = datetime.combine(dummy_date, hora_actual)
            dt_siguiente = dt_actual + timedelta(hours=1)
            hora_siguiente = dt_siguiente.time()
            
            if hora_siguiente > hora_final and hora_siguiente != time(0, 0):
                hora_siguiente = hora_final 

            ocupado = False
            estado = 'LIBRE'

            for r in reservas_del_dia:
                if r.hora_inicio < hora_siguiente and r.hora_fin > hora_actual:
                    ocupado = True
                    estado = 'PENDIENTE' if r.estado == 'PENDIENTE' else 'OCUPADO'
                    break
            
            if not ocupado:
                for p in partidos_del_dia:
                    if p.fecha_hora:
                        p_inicio = p.fecha_hora.time()
                        p_fin = (p.fecha_hora + timedelta(hours=2)).time()
                        
                        if p_inicio < hora_siguiente and p_fin > hora_actual:
                            ocupado = True
                            estado = 'TORNEO'
                            break

            horarios_disponibles.append({
                'hora_mostrar': f"{hora_actual.strftime('%H:%M')} - {hora_siguiente.strftime('%H:%M')}",
                'valor_inicio': hora_actual.strftime('%H:%M'),
                'valor_fin': hora_siguiente.strftime('%H:%M'),
                'precio': tarifa.precio,
                'estado': estado
            })

            hora_actual = hora_siguiente

    if request.method == 'POST':
        hora_inicio_str = request.POST.get('hora_inicio')
        hora_fin_str = request.POST.get('hora_fin')
        fecha_str_post = request.POST.get('fecha')
        
        if hora_inicio_str and hora_fin_str and fecha_str_post:
            hora_inicio_post = datetime.strptime(hora_inicio_str, '%H:%M').time()
            
            horario_seleccionado = HorarioCancha.objects.filter(
                hora_inicio__lte=hora_inicio_post, 
                hora_fin__gt=hora_inicio_post
            ).first()
            
            precio_final = str(horario_seleccionado.precio) if horario_seleccionado else "5.00"
            
            request.session['reserva_pendiente'] = {
                'fecha': fecha_str_post,
                'hora_inicio': hora_inicio_str,
                'hora_fin': hora_fin_str,
                'precio_fijo': precio_final
            }
            return redirect('checkout_pago')
        else:
            messages.error(request, "⚠️ Error: Faltan datos en la selección.")
            
    else:
        form = ReservaCanchaForm(initial={'fecha': fecha_consulta})

    return render(request, 'core/reservar_cancha.html', {
        'form': form, 
        'horarios': horarios_disponibles,
        'fecha_seleccionada': fecha_consulta, 
        'manana': manana 
    })

@login_required
def checkout_pago(request):
    reserva_data = request.session.get('reserva_pendiente')
    if not reserva_data:
        messages.warning(request, "No tienes ninguna reserva en proceso.")
        return redirect('reservar_cancha')

    if request.method == 'POST':
        h_inicio = str(reserva_data['hora_inicio'])
        h_fin = str(reserva_data['hora_fin'])
        
        if len(h_inicio) == 5: h_inicio += ':00'
        if len(h_fin) == 5: h_fin += ':00'

        precio_final = reserva_data.get('precio_total', reserva_data.get('precio_fijo', 5))

        reserva = ReservaCancha.objects.create(
            usuario=request.user,
            fecha=reserva_data['fecha'],
            hora_inicio=h_inicio,
            hora_fin=h_fin,
            precio_total=precio_final,
            estado='PENDIENTE'
        )

        del request.session['reserva_pendiente']

        telefono_cliente = request.user.perfil.telefono if hasattr(request.user, 'perfil') and request.user.perfil.telefono else "No registrado"
        nombre_cliente = f"{request.user.first_name} {request.user.last_name}".strip()
        if not nombre_cliente:
            nombre_cliente = request.user.username

        # ENVIAR CORREO AL ORGANIZADOR
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            asunto = f"📅 NUEVA RESERVA: Cancha el {reserva_data['fecha']}"
            mensaje_correo = f"""
¡Hola Organizador!
Alguien acaba de agendar un turno en la cancha.
Cliente: {nombre_cliente}
Celular: {telefono_cliente}
Fecha: {reserva_data['fecha']}
Horario: {reserva_data['hora_inicio']} a {reserva_data['hora_fin']}
Total a cobrar: ${precio_final}
            """
            send_mail(
                subject=asunto, 
                message=mensaje_correo,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=['TU_CORREO_AQUI@gmail.com'], 
                fail_silently=True
            )
        except Exception as e:
            print("Error enviando email de reserva:", e)

        mensaje = (
            f" *NUEVA RESERVA - CANCHA EL CHULO* \n\n"
            f" *Cliente:* {nombre_cliente}\n"
            f" *Celular:* {telefono_cliente}\n"
            f" *Fecha:* {reserva_data['fecha']}\n"
            f" *Horario:* {reserva_data['hora_inicio']} a {reserva_data['hora_fin']}\n"
            f" *Total a pagar:* ${precio_final}\n\n"
            f"Hola, adjunto el comprobante de transferencia para confirmar mi turno."
        )

        numero_organizador = "593964049283" 
        mensaje_codificado = urllib.parse.quote(mensaje)
        url_whatsapp = f"https://wa.me/{numero_organizador}?text={mensaje_codificado}"

        return render(request, 'core/reserva_exitosa.html', {'url_whatsapp': url_whatsapp, 'reserva': reserva})

    return render(request, 'core/checkout_pago.html', {'reserva': reserva_data})


@login_required
def aprobar_reserva_admin(request, reserva_id):
    if request.user.perfil.rol != 'ORG':
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('dashboard')
        
    reserva = get_object_or_404(ReservaCancha, id=reserva_id)
    reserva.estado = 'ACTIVA'
    reserva.pagado = True 
    reserva.save()
    
    messages.success(request, f'✅ Turno de {reserva.usuario.first_name} aprobado y confirmado exitosamente.')
    return redirect('dashboard')

@login_required
def mis_reservas(request):
    reservas = ReservaCancha.objects.filter(usuario=request.user).order_by('-fecha')
    return render(request, 'core/mis_reservas.html', {'reservas': reservas})

def ver_torneos_activos(request):
    torneos = Torneo.objects.filter(activo=True, inscripcion_abierta=True)
    
    mis_torneos_ids = []
    if request.user.is_authenticated:
        mis_torneos_ids = list(Equipo.objects.filter(dirigente=request.user).values_list('torneo_id', flat=True))

    return render(request, 'core/ver_torneos_activos.html', {
        'torneos': torneos,
        'mis_torneos_ids': mis_torneos_ids 
    })


@login_required
def solicitar_inscripcion(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    ya_inscrito = Equipo.objects.filter(torneo=torneo, dirigente=request.user).exists()
    if ya_inscrito:
        messages.warning(request, 'Ya tienes un equipo inscrito o en proceso para este torneo.')
        return redirect('ver_torneos_activos')

    if request.method == 'POST':
        form = EquipoSolicitudForm(request.POST, request.FILES) 
        if form.is_valid():
            equipo = form.save(commit=False)
            equipo.torneo = torneo
            equipo.dirigente = request.user
            equipo.estado_inscripcion = 'PENDIENTE' 
            equipo.puede_fichar = False              
            equipo.save()

            costo_inscripcion = getattr(torneo, 'precio_inscripcion', Decimal('50.00')) 

            Sancion.objects.get_or_create(
                equipo=equipo,
                torneo=torneo,
                descripcion=f"Inscripción - {torneo.nombre}",
                defaults={
                    'tipo': 'ADMIN',
                    'monto': costo_inscripcion,
                    'monto_pagado': Decimal('0.00'),
                    'pagada': False
                }
            )
            
            if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'FAN':
                request.user.perfil.rol = 'DIR'
                request.user.perfil.save()
            
            try:
                from django.core.mail import send_mail
                from django.conf import settings
                
                asunto = f"🏆 NUEVA SOLICITUD: {equipo.nombre} quiere unirse"
                telefono_dt = getattr(equipo, 'telefono_contacto', 'No ingresó celular')
                
                mensaje = f"""
¡Hola Organizador!
Tienes una nueva solicitud de inscripción.
Torneo: {torneo.nombre}
Equipo: {equipo.nombre}
                """
                
                send_mail(
                    subject=asunto,
                    message=mensaje,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=['TU_CORREO_AQUI@gmail.com'], 
                    fail_silently=True 
                )
            except Exception as e:
                print("Error enviando email:", e)
                
            messages.success(request, '✅ Solicitud enviada con éxito. Tu equipo está PENDIENTE de aprobación y el organizador fue notificado.')
            return redirect('ver_torneos_activos') 
    else:
        form = EquipoSolicitudForm()

    return render(request, 'core/solicitar_inscripcion.html', {'form': form, 'torneo': torneo})


@login_required
@user_passes_test(es_organizador)
def gestionar_solicitudes(request):
    solicitudes = Equipo.objects.filter(estado_inscripcion='PENDIENTE').select_related('torneo', 'dirigente')
    
    if request.method == 'POST':
        equipo_id = request.POST.get('equipo_id')
        accion = request.POST.get('accion') 
        
        equipo = get_object_or_404(Equipo, id=equipo_id)
        
        if accion == 'APROBAR':
            equipo.estado_inscripcion = 'APROBADO'
            equipo.puede_fichar = True  
            equipo.save()
            messages.success(request, f'✅ {equipo.nombre} APROBADO. Ya pueden fichar jugadores.')

        elif accion == 'RECHAZAR':
            equipo.estado_inscripcion = 'RECHAZADO'
            equipo.save()
            messages.warning(request, f'Solicitud de {equipo.nombre} rechazada.')
            
        return redirect('gestionar_solicitudes')

    return render(request, 'core/gestionar_solicitudes.html', {'solicitudes': solicitudes})

def ver_carrito(request):
    reserva_session = request.session.get('reserva_pendiente')
    
    if not reserva_session:
        messages.info(request, "Tu carrito está vacío.")
        return redirect('reservar_cancha')

    ctx = {
        'fecha': reserva_session.get('fecha'),
        'inicio': reserva_session.get('hora_inicio'),
        'fin': reserva_session.get('hora_fin'),
    }
    return render(request, 'core/carrito.html', ctx)


@login_required
def cancelar_reserva(request, reserva_id):
    reserva = get_object_or_404(ReservaCancha, id=reserva_id)
    
    if request.user != reserva.usuario and request.user.perfil.rol != 'ORG':
        messages.error(request, "No tienes permiso para cancelar esta reserva.")
        return redirect('mis_reservas')

    fecha_reserva = reserva.fecha 
    fecha_hoy = timezone.now().date()
    dias_faltantes = (fecha_reserva - fecha_hoy).days
    
    if dias_faltantes <= 2:
        multa = float(reserva.precio_total) * 0.50
        mensaje = f"⚠️ Cancelación tardía (faltan {dias_faltantes} días). Se aplicó multa del 50%."
    else:
        multa = 0
        mensaje = "✅ Cancelación a tiempo. Reembolso completo."

    reembolso = float(reserva.precio_total) - multa

    if request.method == 'POST':
        reserva.estado = 'CANCELADA'
        reserva.monto_reembolso = reembolso
        reserva.save()
        messages.info(request, f"Reserva Cancelada. {mensaje} Reembolso: ${reembolso}")
        return redirect('mis_reservas')

    return render(request, 'core/confirmar_cancelacion.html', {
        'objeto': reserva, 
        'tipo': 'Reserva de Cancha',
        'multa': multa,
        'reembolso': reembolso,
        'dias': dias_faltantes
    })

@login_required
def cancelar_inscripcion_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    
    if request.user != equipo.dirigente and request.user.perfil.rol != 'ORG':
        return redirect('dashboard')

    precio_inscripcion = float(equipo.torneo.costo_inscripcion)
    
    if equipo.estado_inscripcion == 'APROBADO':
        multa = precio_inscripcion * 0.25
        mensaje = "⚠️ Equipo ya aprobado. Se retiene el 25% por gastos administrativos."
    else:
        multa = 0
        mensaje = "✅ Solicitud cancelada antes de aprobación. Sin costo."

    reembolso = precio_inscripcion - multa

    if request.method == 'POST':
        equipo.estado_inscripcion = 'RECHAZADO' 
        equipo.monto_reembolso = reembolso
        equipo.save()
        messages.info(request, f"Inscripción Cancelada. {mensaje} Reembolso: ${reembolso}")
        return redirect('ver_torneos_activos')

    return render(request, 'core/confirmar_cancelacion.html', {
        'objeto': equipo,
        'tipo': f"Inscripción Equipo {equipo.nombre}",
        'multa': multa,
        'reembolso': reembolso,
        'extra_info': "Estado actual: " + equipo.get_estado_inscripcion_display()
    })

@login_required
def cobrar_sancion(request, sancion_id):
    # PERMITIR AHORA A ORGANIZADORES Y VOCALES DE MESA COBRAR
    if request.user.perfil.rol not in ['ORG', 'VOC']:
        return redirect('dashboard')
        
    sancion = get_object_or_404(Sancion, id=sancion_id)
    
    if request.method == 'POST':
        abono_str = request.POST.get('monto_abono')
        abono = Decimal(abono_str) if abono_str else sancion.saldo
        
        sancion.monto_pagado += abono
        
        if sancion.monto_pagado >= sancion.monto:
            sancion.pagada = True
            sancion.monto_pagado = sancion.monto 
            messages.success(request, f"✅ ¡Deuda de {sancion.equipo.nombre} cancelada en su totalidad!")
        else:
            messages.success(request, f"💰 Abono de ${abono} registrado. Saldo pendiente: ${sancion.saldo}")
            
        sancion.save()

        AbonoSancion.objects.create(
            sancion=sancion,
            monto=abono
        )
        
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
def gestionar_finanzas(request):
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')
        
    if request.method == 'POST' and 'generar_inscripciones_viejas' in request.POST:
        equipos_aprobados = Equipo.objects.filter(estado_inscripcion='APROBADO')
        agregados = 0
        for eq in equipos_aprobados:
            ya_cobrado = Sancion.objects.filter(equipo=eq, descripcion__icontains='Inscripci').exists()
            if not ya_cobrado:
                Sancion.objects.create(
                    torneo=eq.torneo,
                    equipo=eq,
                    tipo='ADMIN',
                    monto=getattr(eq.torneo, 'precio_inscripcion', Decimal('50.00')),
                    monto_pagado=Decimal('0.00'),
                    descripcion=f"Inscripción al Torneo {eq.torneo.nombre}",
                    pagada=False
                )
                agregados += 1
        
        messages.success(request, f'✅ Se generaron {agregados} recibos de inscripción para los equipos antiguos.')
        return redirect('gestionar_finanzas')

    total_reservas = ReservaCancha.objects.filter(estado='ACTIVA', es_torneo=False).aggregate(Sum('precio_total'))['precio_total__sum'] or Decimal('0.00')
    
    inscripciones = Sancion.objects.filter(descripcion__icontains='Inscripci')
    
    inscripciones_pagadas_totalmente = inscripciones.filter(pagada=True).aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
    abonos_inscripciones = inscripciones.filter(pagada=False).aggregate(Sum('monto_pagado'))['monto_pagado__sum'] or Decimal('0.00')
    dinero_real_inscripciones = inscripciones_pagadas_totalmente + abonos_inscripciones
    
    inscripciones_pendientes = inscripciones.filter(pagada=False).aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
    saldo_real_inscripciones = inscripciones_pendientes - abonos_inscripciones
    
    multas = Sancion.objects.exclude(descripcion__icontains='Inscripci')
    
    multas_pagadas_totalmente = multas.filter(pagada=True).aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
    abonos_multas = multas.filter(pagada=False).aggregate(Sum('monto_pagado'))['monto_pagado__sum'] or Decimal('0.00')
    dinero_real_multas = multas_pagadas_totalmente + abonos_multas
    
    multas_pendientes = multas.filter(pagada=False).aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
    saldo_real_multas = multas_pendientes - abonos_multas
    
    lista_sanciones = Sancion.objects.all().select_related('equipo').order_by('pagada', '-id')

    ctx = {
        'ingreso_canchas': float(total_reservas),
        'inscripciones_pagadas': float(dinero_real_inscripciones),
        'inscripciones_pendientes': float(saldo_real_inscripciones),
        'multas_pagadas': float(dinero_real_multas),
        'multas_pendientes': float(saldo_real_multas),
        'total_caja': float(total_reservas + dinero_real_inscripciones + dinero_real_multas),
        'sanciones': lista_sanciones
    }
    return render(request, 'core/gestionar_finanzas.html', ctx)

@login_required
def admin_gestion_jugadores(request):
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')
        
    query = request.GET.get('q')
    jugadores = Jugador.objects.all().select_related('equipo').order_by('equipo', 'dorsal')
    
    if query:
        jugadores = jugadores.filter(
            Q(nombres__icontains=query) |  
            Q(equipo__nombre__icontains=query) |
            Q(cedula__icontains=query)
        )

    return render(request, 'core/admin_jugadores.html', {'jugadores': jugadores})

@login_required
def admin_gestion_usuarios(request):
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')

    if request.method == 'POST':
        perfil_id = request.POST.get('perfil_id')
        nuevo_rol = request.POST.get('nuevo_rol')
        
        if perfil_id and nuevo_rol:
            perfil_usuario = get_object_or_404(Perfil, id=perfil_id)
            
            if perfil_usuario.usuario == request.user:
                messages.error(request, "No puedes cambiar tu propio rol aquí.")
            else:
                perfil_usuario.rol = nuevo_rol
                perfil_usuario.save()
                messages.success(request, f'Rol de "{perfil_usuario.usuario.username}" actualizado a {perfil_usuario.get_rol_display()}.')
            
            return redirect('admin_gestion_usuarios')

    usuarios = User.objects.all().select_related('perfil').order_by('-date_joined')
    
    return render(request, 'core/admin_usuarios.html', {'usuarios': usuarios})

# =========================================================
# VISTAS RESTAURADAS (Horarios, Medios y Próxima Jornada)
# =========================================================

@login_required
@user_passes_test(es_organizador)
def gestionar_horarios(request):
    horarios = HorarioCancha.objects.all().order_by('hora_inicio')
    if request.method == 'POST':
        form = HorarioCanchaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Horario y tarifa agregados correctamente.')
            return redirect('gestionar_horarios')
        else:
            for campo, errores in form.errors.items():
                for error in errores:
                    messages.error(request, f"❌ Error en {campo}: {error}")
    else:
        form = HorarioCanchaForm()
    return render(request, 'core/gestionar_horarios.html', {'form': form, 'horarios': horarios})

@login_required
@user_passes_test(es_organizador)
def eliminar_horario(request, horario_id):
    horario = get_object_or_404(HorarioCancha, id=horario_id)
    hora_str = horario.hora_inicio.strftime('%H:%M')
    horario.delete()
    messages.warning(request, f'🗑️ El bloque de las {hora_str} ha sido eliminado.')
    return redirect('gestionar_horarios')

@login_required
@user_passes_test(es_organizador)
def gestionar_medios(request):
    fotos = FotoGaleria.objects.all().order_by('orden', '-id')
    publicidades = Publicidad.objects.all().order_by('-id')

    if request.method == 'POST':
        if 'btn_foto' in request.POST:
            form_foto = FotoGaleriaForm(request.POST, request.FILES)
            if form_foto.is_valid():
                form_foto.save()
                messages.success(request, '📸 Foto agregada a la galería con éxito.')
                return redirect('gestionar_medios')
        elif 'btn_publi' in request.POST:
            form_publi = PublicidadForm(request.POST, request.FILES)
            if form_publi.is_valid():
                form_publi.save()
                messages.success(request, '📢 Publicidad agregada correctamente.')
                return redirect('gestionar_medios')

    form_foto = FotoGaleriaForm()
    form_publi = PublicidadForm()
    return render(request, 'core/gestionar_medios.html', {
        'fotos': fotos, 'publicidades': publicidades, 'form_foto': form_foto, 'form_publi': form_publi
    })

@login_required
@user_passes_test(es_organizador)
def eliminar_foto(request, foto_id):
    foto = get_object_or_404(FotoGaleria, id=foto_id)
    foto.delete()
    messages.warning(request, "🗑️ Foto eliminada.")
    return redirect('gestionar_medios')

@login_required
@user_passes_test(es_organizador)
def eliminar_publicidad(request, pub_id):
    pub = get_object_or_404(Publicidad, id=pub_id)
    pub.delete()
    messages.warning(request, "🗑️ Publicidad eliminada.")
    return redirect('gestionar_medios')

@login_required
def proxima_jornada(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    partidos_futuros = Partido.objects.filter(torneo=torneo, estado='PROG').exclude(fecha_hora__isnull=True).order_by('fecha_hora')
    partidos_mostrar = []
    jornada_num = None
    etapa_nombre = None

    if partidos_futuros.exists():
        prox_partido = partidos_futuros.first()
        jornada_num = prox_partido.numero_fecha
        etapa_nombre = prox_partido.get_etapa_display()
        partidos_mostrar = Partido.objects.filter(torneo=torneo, etapa=prox_partido.etapa, numero_fecha=jornada_num).order_by('fecha_hora')
    else:
        partidos_pendientes = Partido.objects.filter(torneo=torneo, estado='PROG').order_by('etapa', 'numero_fecha')
        if partidos_pendientes.exists():
            prox_partido = partidos_pendientes.first()
            jornada_num = prox_partido.numero_fecha
            etapa_nombre = prox_partido.get_etapa_display()
            partidos_mostrar = Partido.objects.filter(torneo=torneo, etapa=prox_partido.etapa, numero_fecha=jornada_num).order_by('id')
            
    return render(request, 'core/proxima_jornada.html', {'torneo': torneo, 'partidos': partidos_mostrar, 'jornada': jornada_num, 'etapa': etapa_nombre})


# =========================================================
# 8. GENERADOR AUTOMÁTICO DE FIXTURES (ALGORITMO DE RUEDA)
# =========================================================

@login_required
@user_passes_test(es_organizador)
def generar_fixture(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    equipos = list(Equipo.objects.filter(torneo=torneo, estado_inscripcion='APROBADO'))
    
    if len(equipos) < 2:
        messages.error(request, "Necesitas al menos 2 equipos APROBADOS para generar un fixture.")
        return redirect('gestionar_torneos')

    if len(equipos) % 2 != 0:
        equipos.append(None) 
    
    n = len(equipos)
    fixture = []
    equipos_rotacion = equipos.copy()

    for fecha in range(1, n):
        partidos_fecha = []
        for i in range(n // 2):
            local = equipos_rotacion[i]
            visita = equipos_rotacion[n - 1 - i]
            if local is not None and visita is not None:
                if i == 0 and fecha % 2 == 0: partidos_fecha.append({'local': visita, 'visita': local})
                else: partidos_fecha.append({'local': local, 'visita': visita})
        
        fixture.append({'numero_fecha': fecha, 'partidos': partidos_fecha})
        equipos_rotacion.insert(1, equipos_rotacion.pop())

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'guardar_db':
            partidos_creados = 0
            for jornada in fixture:
                num_fecha = jornada['numero_fecha']
                for p in jornada['partidos']:
                    existe = Partido.objects.filter(torneo=torneo, etapa='F1', equipo_local=p['local'], equipo_visita=p['visita']).exists()
                    if not existe:
                        Partido.objects.create(torneo=torneo, etapa='F1', numero_fecha=num_fecha, equipo_local=p['local'], equipo_visita=p['visita'], estado='PROG', fecha_hora=None)
                        partidos_creados += 1
            messages.success(request, f'✅ Fixture generado: {partidos_creados} partidos creados en el calendario. Ahora puedes asignarles fecha y hora.')
            return redirect(f"/programar/?torneo={torneo.id}")
            
        elif accion == 'descargar_pdf':
            template_path = 'core/fixture_pdf.html'
            context = {'torneo': torneo, 'fixture': fixture}
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Fixture_{torneo.nombre}.pdf"'
            template = get_template(template_path)
            html = template.render(context)
            pisa_status = pisa.CreatePDF(html, dest=response)
            if pisa_status.err: return HttpResponse('Error al generar PDF <pre>' + html + '</pre>')
            return response

    return render(request, 'core/generar_fixture.html', {'torneo': torneo, 'fixture': fixture, 'total_equipos': len(equipos) if None not in equipos else (len(equipos) - 1)})

# =========================================================
# 9. MAGIA: CUARTOS, SEMIS Y FINALES (LLAVES PROFESIONALES)
# =========================================================

def obtener_clasificados_fase2(torneo, letra_grupo):
    equipos_grupo = Equipo.objects.filter(torneo=torneo, grupo_fase2=letra_grupo, estado_inscripcion='APROBADO')
    lista_tabla = []
    for equipo in equipos_grupo:
        partidos = Partido.objects.filter(Q(equipo_local=equipo) | Q(equipo_visita=equipo), estado__in=['JUG', 'WO', 'FINALIZADO'], etapa='F2')
        pj=0; pg=0; pe=0; gf=0; gc=0
        for p in partidos:
            pj+=1
            es_local = (p.equipo_local == equipo)
            goles_pro = p.goles_local if es_local else p.goles_visita
            goles_rival = p.goles_visita if es_local else p.goles_local
            gf+=goles_pro; gc+=goles_rival
            if goles_pro > goles_rival: pg+=1
            elif goles_pro == goles_rival: pe+=1
        pts = (pg * 3) + (pe * 1) + equipo.puntos_bonificacion
        lista_tabla.append({'equipo': equipo, 'pts': pts, 'gd': gf-gc, 'gf': gf})
    return sorted(lista_tabla, key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)[:4]

def obtener_ganador_llave(torneo, etapa, eq1, eq2):
    partidos = Partido.objects.filter(torneo=torneo, etapa=etapa, equipo_local__in=[eq1, eq2], equipo_visita__in=[eq1, eq2])
    if not partidos.exists(): return None
    
    for p in partidos:
        if p.estado not in ['JUG', 'WO', 'FINALIZADO']: return None

    goles_eq1 = 0; goles_eq2 = 0; penales_eq1 = 0; penales_eq2 = 0

    for p in partidos:
        if p.equipo_local == eq1:
            goles_eq1 += p.goles_local; goles_eq2 += p.goles_visita
            if p.hubo_penales: penales_eq1 += p.penales_local; penales_eq2 += p.penales_visita
        else:
            goles_eq1 += p.goles_visita; goles_eq2 += p.goles_local
            if p.hubo_penales: penales_eq1 += p.penales_visita; penales_eq2 += p.penales_local

    if goles_eq1 > goles_eq2: return eq1
    elif goles_eq2 > goles_eq1: return eq2
    else:
        if penales_eq1 > penales_eq2: return eq1
        elif penales_eq2 > penales_eq1: return eq2
    return None 

@login_required
@user_passes_test(es_organizador)
def generar_cuartos_final(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if Partido.objects.filter(torneo=torneo, etapa='4TOS').exists():
        messages.error(request, "Los Cuartos de Final ya fueron generados.")
        return redirect(f"/programar/?torneo={torneo.id}")

    ida_y_vuelta = request.POST.get('ida_y_vuelta') == 'on'
    torneo.fase3_ida_vuelta = ida_y_vuelta
    torneo.save()

    clasificados_a = obtener_clasificados_fase2(torneo, 'A')
    clasificados_b = obtener_clasificados_fase2(torneo, 'B')

    if len(clasificados_a) < 4 or len(clasificados_b) < 4:
        messages.error(request, "Aún no hay 4 equipos clasificados en cada grupo.")
        return redirect('tabla_posiciones_f2', torneo_id=torneo.id)

    cruces = [
        (clasificados_a[0]['equipo'], clasificados_b[3]['equipo']), 
        (clasificados_a[1]['equipo'], clasificados_b[2]['equipo']), 
        (clasificados_a[2]['equipo'], clasificados_b[1]['equipo']), 
        (clasificados_a[3]['equipo'], clasificados_b[0]['equipo'])  
    ]

    partidos_creados = 0
    with transaction.atomic():
        for local, visita in cruces:
            Partido.objects.create(torneo=torneo, etapa='4TOS', numero_fecha=1, equipo_local=local, equipo_visita=visita)
            partidos_creados += 1
            if torneo.fase3_ida_vuelta:
                Partido.objects.create(torneo=torneo, etapa='4TOS', numero_fecha=2, equipo_local=visita, equipo_visita=local)
                partidos_creados += 1

    formato_texto = "Ida y Vuelta" if ida_y_vuelta else "Partido Único"
    messages.success(request, f'✅ Cuartos de Final generados con éxito ({formato_texto}). Se crearon {partidos_creados} partidos.')
    return redirect(f"/programar/?torneo={torneo.id}")

@login_required
@user_passes_test(es_organizador)
def generar_semifinales(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if Partido.objects.filter(torneo=torneo, etapa='SEMI').exists():
        messages.error(request, "Las Semifinales ya fueron generadas.")
        return redirect(f"/programar/?torneo={torneo.id}")
    
    clas_a = obtener_clasificados_fase2(torneo, 'A')
    clas_b = obtener_clasificados_fase2(torneo, 'B')
    
    g_s1 = obtener_ganador_llave(torneo, '4TOS', clas_a[0]['equipo'], clas_b[3]['equipo']) 
    g_s2 = obtener_ganador_llave(torneo, '4TOS', clas_a[1]['equipo'], clas_b[2]['equipo']) 
    g_s3 = obtener_ganador_llave(torneo, '4TOS', clas_a[2]['equipo'], clas_b[1]['equipo']) 
    g_s4 = obtener_ganador_llave(torneo, '4TOS', clas_a[3]['equipo'], clas_b[0]['equipo']) 

    if not (g_s1 and g_s2 and g_s3 and g_s4):
        messages.error(request, "Aún no terminan los Cuartos, o hay empates globales sin definir por penales en el Acta.")
        return redirect(f"/programar/?torneo={torneo.id}")

    with transaction.atomic():
        Partido.objects.create(torneo=torneo, etapa='SEMI', equipo_local=g_s1, equipo_visita=g_s3)
        Partido.objects.create(torneo=torneo, etapa='SEMI', equipo_local=g_s4, equipo_visita=g_s2)

    messages.success(request, '✅ Semifinales (a partido único) generadas con éxito.')
    return redirect(f"/programar/?torneo={torneo.id}")

@login_required
@user_passes_test(es_organizador)
def generar_finales(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if Partido.objects.filter(torneo=torneo, etapa='FINAL').exists():
        messages.error(request, "Las Finales ya fueron generadas.")
        return redirect(f"/programar/?torneo={torneo.id}")

    semis = Partido.objects.filter(torneo=torneo, etapa='SEMI')
    if semis.count() != 2:
        messages.error(request, "Faltan datos de las semifinales.")
        return redirect(f"/programar/?torneo={torneo.id}")

    ganadores = []; perdedores = []
    for s in semis:
        if s.estado not in ['JUG', 'WO', 'FINALIZADO']:
            messages.error(request, "Las semifinales aún no han concluido o falta firmar el acta.")
            return redirect(f"/programar/?torneo={torneo.id}")
        
        goles_l = s.goles_local; goles_v = s.goles_visita
        pen_l = s.penales_local if s.hubo_penales else 0
        pen_v = s.penales_visita if s.hubo_penales else 0

        if goles_l > goles_v or (goles_l == goles_v and pen_l > pen_v):
            ganadores.append(s.equipo_local)
            perdedores.append(s.equipo_visita)
        else:
            ganadores.append(s.equipo_visita)
            perdedores.append(s.equipo_local)

    with transaction.atomic():
        Partido.objects.create(torneo=torneo, etapa='TERC', equipo_local=perdedores[0], equipo_visita=perdedores[1])
        Partido.objects.create(torneo=torneo, etapa='FINAL', equipo_local=ganadores[0], equipo_visita=ganadores[1])

    messages.success(request, '🏆 ¡Gran Final y 3er Lugar generados!')
    return redirect(f"/programar/?torneo={torneo.id}")

def llaves_eliminatorias(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    cuartos = Partido.objects.filter(torneo=torneo, etapa='4TOS').order_by('numero_fecha', 'id')
    semis = Partido.objects.filter(torneo=torneo, etapa='SEMI').order_by('numero_fecha', 'id')
    tercer = Partido.objects.filter(torneo=torneo, etapa='TERC').first()
    final = Partido.objects.filter(torneo=torneo, etapa='FINAL').first()
    return render(request, 'core/llaves_eliminatorias.html', {
        'torneo': torneo, 'cuartos': cuartos, 'semis': semis, 'tercer': tercer, 'final': final
    })

# =========================================================
# NUEVAS FUNCIONES: FASE 2 Y REVERSOS
# =========================================================

# =========================================================
# FASE 2: FIXTURE Y REVERSO
# =========================================================

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def revertir_fase2(request, torneo_id):
    """ Deshace la creación de los grupos de la Fase 2 """
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if request.method == 'POST':
        with transaction.atomic():
            # 1. Borramos todos los partidos programados de la Fase 2
            Partido.objects.filter(torneo=torneo, etapa='F2').delete()
            # 2. Le quitamos el Grupo A y B a los equipos. Usamos "" para evitar el error NOT NULL
            Equipo.objects.filter(torneo=torneo).update(grupo_fase2="")
            
        messages.warning(request, "🔄 Reverso exitoso: Se eliminaron los Grupos A y B de la Fase 2.")
    return redirect('tabla_posiciones', torneo_id=torneo.id)

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def revertir_llaves(request, torneo_id):
    """ Deshace la creación de Cuartos, Semis y Finales """
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if request.method == 'POST':
        with transaction.atomic():
            # Borramos cualquier partido que pertenezca a la etapa eliminatoria
            Partido.objects.filter(torneo=torneo, etapa__in=['4TOS', 'SEMI', 'TERC', 'FINAL']).delete()
            
        messages.warning(request, "🔄 Reverso exitoso: Se eliminaron las llaves eliminatorias.")
    return redirect('tabla_posiciones_f2', torneo_id=torneo.id)

@login_required
@user_passes_test(es_organizador)
def generar_fixture_fase2(request, torneo_id):
    """ Genera el fixture intercalado A-B con rotación de horarios justa """
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    equipos_a = list(Equipo.objects.filter(torneo=torneo, grupo_fase2='A', estado_inscripcion='APROBADO'))
    equipos_b = list(Equipo.objects.filter(torneo=torneo, grupo_fase2='B', estado_inscripcion='APROBADO'))
    
    if not equipos_a or not equipos_b:
        messages.error(request, "⚠️ Faltan equipos en los grupos. Debes generar la Fase 2 primero.")
        return redirect('tabla_posiciones_f2', torneo_id=torneo.id)

    def crear_fixture_grupo(equipos_grupo):
        if len(equipos_grupo) % 2 != 0:
            equipos_grupo.append(None) # Descanso
        n = len(equipos_grupo)
        fix = []
        rotacion = equipos_grupo.copy()
        
        for fecha in range(1, n):
            partidos_fecha = []
            for i in range(n // 2):
                local = rotacion[i]
                visita = rotacion[n - 1 - i]
                if local is not None and visita is not None:
                    # Alternar localía
                    if i == 0 and fecha % 2 == 0:
                        partidos_fecha.append({'local': visita, 'visita': local})
                    else:
                        partidos_fecha.append({'local': local, 'visita': visita})
            
            # ✨ MAGIA 1: ROTACIÓN DE HORARIOS JUSTA ✨
            # Rotamos la lista de partidos de esta fecha para que los equipos
            # no jueguen siempre en el mismo orden (ej. a primera hora).
            if partidos_fecha:
                shift = fecha % len(partidos_fecha)
                partidos_fecha = partidos_fecha[shift:] + partidos_fecha[:shift]
                
            fix.append(partidos_fecha)
            rotacion.insert(1, rotacion.pop())
        return fix

    # Creamos fixtures base por grupo
    fix_a = crear_fixture_grupo(equipos_a)
    fix_b = crear_fixture_grupo(equipos_b)
    
    # ✨ MAGIA 2 y 3: INTERCALADO Y ALTERNANCIA SEMANAL ✨
    max_fechas = max(len(fix_a), len(fix_b))
    fixture_combinado = []
    
    for f in range(max_fechas):
        partidos_comb = []
        p_a = fix_a[f] if f < len(fix_a) else []
        p_b = fix_b[f] if f < len(fix_b) else []
        
        semana = f + 1
        empieza_grupo_A = (semana % 2 != 0) # Impar (1,3,5) empieza A. Par (2,4,6) empieza B.
        
        max_partidos_dia = max(len(p_a), len(p_b))
        
        for i in range(max_partidos_dia):
            if empieza_grupo_A:
                if i < len(p_a): partidos_comb.append(p_a[i]) # Va A
                if i < len(p_b): partidos_comb.append(p_b[i]) # Va B
            else:
                if i < len(p_b): partidos_comb.append(p_b[i]) # Va B
                if i < len(p_a): partidos_comb.append(p_a[i]) # Va A
                
        fixture_combinado.append({'numero_fecha': semana, 'partidos': partidos_comb})

    # Lógica de Ida y Vuelta
    if torneo.fase2_ida_vuelta:
        fixture_vuelta = []
        num_fechas_ida = len(fixture_combinado)
        for f_index, jornada in enumerate(fixture_combinado):
            partidos_vuelta = []
            for p in jornada['partidos']:
                partidos_vuelta.append({'local': p['visita'], 'visita': p['local']})
            fixture_vuelta.append({'numero_fecha': num_fechas_ida + f_index + 1, 'partidos': partidos_vuelta})
        fixture_combinado.extend(fixture_vuelta)

    # Procesar guardado
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'guardar_db':
            Partido.objects.filter(torneo=torneo, etapa='F2').delete() # Reverso
            
            partidos_creados = 0
            with transaction.atomic():
                for jornada in fixture_combinado:
                    num_fecha = jornada['numero_fecha']
                    for p in jornada['partidos']:
                        Partido.objects.create(
                            torneo=torneo, 
                            etapa='F2', 
                            numero_fecha=num_fecha, 
                            equipo_local=p['local'], 
                            equipo_visita=p['visita'], 
                            estado='PROG', 
                            fecha_hora=None 
                        )
                        partidos_creados += 1
            
            messages.success(request, f'✅ ¡Fixture Fase 2 Generado! Se intercalaron horarios y grupos ({partidos_creados} partidos en total).')
            return redirect(f"/programar/?torneo={torneo.id}")

    return render(request, 'core/generar_fixture_fase2.html', {
        'torneo': torneo, 
        'fixture': fixture_combinado,
        'ida_vuelta': torneo.fase2_ida_vuelta
    })

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def generar_segunda_vuelta_f1(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    if request.method == 'POST':
        # 1. Obtenemos cómo quedó la tabla de la Vuelta 1 exactamente
        # Reutilizamos tu lógica matemática para saber el Top 2
        equipos = Equipo.objects.filter(torneo=torneo, estado_inscripcion='APROBADO')
        tabla_v1 = []
        for eq in equipos:
            partidos_v1 = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=1, estado__in=['JUG', 'WO']).filter(Q(equipo_local=eq) | Q(equipo_visita=eq))
            pts = sum([3 if (p.equipo_local == eq and p.goles_local > p.goles_visita) or (p.equipo_visita == eq and p.goles_visita > p.goles_local) else 1 if p.goles_local == p.goles_visita else 0 for p in partidos_v1])
            gd = sum([p.goles_local - p.goles_visita if p.equipo_local == eq else p.goles_visita - p.goles_local for p in partidos_v1])
            tabla_v1.append({'equipo': eq, 'pts': pts, 'gd': gd})
            
        tabla_v1 = sorted(tabla_v1, key=lambda x: (x['pts'], x['gd']), reverse=True)
        
        with transaction.atomic():
            # 2. Damos bonificaciones a los dos primeros (2 pts al primero, 1 pt al segundo)
            if len(tabla_v1) > 0:
                eq1 = tabla_v1[0]['equipo']
                eq1.puntos_bonificacion += 2
                eq1.save()
            if len(tabla_v1) > 1:
                eq2 = tabla_v1[1]['equipo']
                eq2.puntos_bonificacion += 1
                eq2.save()

            # 3. Copiamos todos los partidos de la Vuelta 1, invertimos la localía y les ponemos vuelta=2
            partidos_ida = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=1)
            for p in partidos_ida:
                Partido.objects.create(
                    torneo=torneo,
                    etapa='F1',
                    vuelta=2,
                    numero_fecha=p.numero_fecha + 10, # Para diferenciar en el calendario
                    equipo_local=p.equipo_visita, # Invertimos
                    equipo_visita=p.equipo_local, # Invertimos
                    estado='PROG',
                    fecha_hora=None
                )
                
        messages.success(request, f"✅ ¡Segunda Vuelta Iniciada! 2pts para {tabla_v1[0]['equipo'].nombre} y 1pt para {tabla_v1[1]['equipo'].nombre}.")
        return redirect('tabla_posiciones', torneo_id=torneo.id)

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def revertir_segunda_vuelta_f1(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    if request.method == 'POST':
        with transaction.atomic():
            # 1. Borramos TODOS los partidos que sean de la Fase 1 y Vuelta 2
            partidos_v2 = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2)
            cantidad_borrada = partidos_v2.count()
            partidos_v2.delete()
            
            # 2. Reseteamos los puntos de bonificación a 0 para todos los equipos de este torneo
            equipos = Equipo.objects.filter(torneo=torneo)
            for eq in equipos:
                if eq.puntos_bonificacion > 0:
                    eq.puntos_bonificacion = 0
                    eq.save()
                    
        messages.warning(request, f"🔄 Reverso exitoso: Se eliminaron {cantidad_borrada} partidos de revancha y se quitaron los bonos.")
        return redirect('tabla_posiciones', torneo_id=torneo.id)
    
@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def generar_llaves(request, torneo_id):
    """ Función esqueleto para generar Cuartos de Final """
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if request.method == 'POST':
        # 🚧 Aquí luego pondremos la lógica matemática para los cruces.
        messages.success(request, "🚧 Botón conectado correctamente. (Falta programar la lógica de los Cuartos de Final).")
        return redirect('tabla_posiciones_f2', torneo_id=torneo.id)
    return redirect('tabla_posiciones_f2', torneo_id=torneo.id)

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def generar_vuelta2_f1(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    if request.method == 'POST':
        with transaction.atomic():
            # 1. Buscamos todos los partidos de la primera vuelta
            partidos_vuelta1 = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=1)
            
            if not partidos_vuelta1.exists():
                messages.error(request, "⛔ No puedes iniciar la 2da Vuelta porque no hay partidos en la 1ra Vuelta.")
                return redirect('tabla_posiciones', torneo_id=torneo.id)

            # 2. Averiguamos cuál fue la última jornada de la Vuelta 1 (ej: Jornada 5)
            ultima_fecha = partidos_vuelta1.aggregate(Max('numero_fecha'))['numero_fecha__max'] or 0
            
            # 3. Generamos el fixture de revancha automáticamente
            partidos_creados = 0
            for p in partidos_vuelta1:
                # OJO: Solo clonamos un partido de revancha si no existe ya
                if not Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2, equipo_local=p.equipo_visita, equipo_visita=p.equipo_local).exists():
                    Partido.objects.create(
                        torneo=torneo,
                        etapa='F1',
                        vuelta=2, # 🔥 Le decimos al sistema que esto es la revancha
                        numero_fecha=p.numero_fecha + ultima_fecha, # Si la V1 terminó en J5, la revancha empieza en J6
                        equipo_local=p.equipo_visita, # 🔄 INVERTIMOS LOCALÍA
                        equipo_visita=p.equipo_local, # 🔄 INVERTIMOS LOCALÍA
                        estado='PROG',
                        cancha=p.cancha
                    )
                    partidos_creados += 1
            
            # 4. (Opcional) Aquí puedes agregar la lógica para sumar los bonos a los equipos top.
            
        messages.success(request, f"✅ ¡Fixture de Revancha generado! Se crearon {partidos_creados} nuevos partidos.")
    return redirect('tabla_posiciones', torneo_id=torneo.id)

@login_required
@user_passes_test(lambda u: u.perfil.rol == 'ORG')
def otorgar_bonos_vuelta2(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    if request.method == 'POST':
        with transaction.atomic():
            # 1. Obtenemos todos los equipos del torneo
            equipos = Equipo.objects.filter(torneo=torneo)
            
            # 2. Calculamos los puntos SOLO de la vuelta 2 para saber quién ganó esta etapa
            ranking = []
            for eq in equipos:
                # Partidos de local en vuelta 2
                locales = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2, equipo_local=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
                # Partidos de visita en vuelta 2
                visitas = Partido.objects.filter(torneo=torneo, etapa='F1', vuelta=2, equipo_visita=eq, estado__in=['FINALIZADO', 'JUG', 'WO'])
                
                puntos = 0
                gd = 0
                for p in locales:
                    if p.goles_local > p.goles_visita: puntos += 3
                    elif p.goles_local == p.goles_visita: puntos += 1
                    gd += (p.goles_local - p.goles_visita)
                    
                for p in visitas:
                    if p.goles_visita > p.goles_local: puntos += 3
                    elif p.goles_visita == p.goles_local: puntos += 1
                    gd += (p.goles_visita - p.goles_local)
                
                ranking.append({'equipo': eq, 'puntos': puntos, 'gd': gd})
            
            # 3. Ordenamos por puntos (y luego por GD para desempatar)
            ranking.sort(key=lambda x: (x['puntos'], x['gd']), reverse=True)
            
            # 4. Asignamos los bonos a los 2 primeros (Si hay al menos 2 equipos)
            if len(ranking) >= 1:
                campeon = ranking[0]['equipo']
                campeon.puntos_bonificacion += 2
                campeon.save()
            if len(ranking) >= 2:
                subcampeon = ranking[1]['equipo']
                subcampeon.puntos_bonificacion += 1
                subcampeon.save()
                
        messages.success(request, f"🏆 ¡Bonificaciones entregadas! +2 pts para {ranking[0]['equipo'].nombre} y +1 pt para {ranking[1]['equipo'].nombre}.")
    return redirect('tabla_posiciones', torneo_id=torneo.id)