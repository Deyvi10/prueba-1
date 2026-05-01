from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from core import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # --- DJANGO ADMIN (Panel Oscuro) ---
    path('admin/', admin.site.urls),

    # ============================================
    # 1. ACCESO Y SEGURIDAD (Login, Registro, Usuarios)
    # ============================================
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Registro Público
    path('registro/', views.registro_publico, name='registro_publico'),
    
    # GESTIÓN DE USUARIOS (Vistas del Organizador)
    path('crear-usuario/', views.crear_usuario, name='crear_usuario'),
    
    # --- CORRECCIÓN AQUÍ: Usamos 'gestion/' para no chocar con 'admin/' ---
    path('gestion/usuarios/', views.admin_gestion_usuarios, name='admin_gestion_usuarios'), 
    path('usuarios/', views.gestionar_usuarios, name='gestionar_usuarios'), # (Ruta antigua opcional)

    # ============================================
    # 2. VISTAS PRINCIPALES (ORGANIZADOR)
    # ============================================
    path('', views.dashboard, name='dashboard'),
    path('torneos/', views.gestionar_torneos, name='gestionar_torneos'),
    
    # Gestión de Equipos
    path('equipos/', views.gestionar_equipos, name='gestionar_equipos'),
    path('equipos/editar/<int:equipo_id>/', views.editar_equipo, name='editar_equipo'),
    path('equipos/eliminar/<int:equipo_id>/', views.eliminar_equipo, name='eliminar_equipo'),
    
    # Gestión de Jugadores
    path('jugadores/', views.gestionar_jugadores, name='gestionar_jugadores'), # Vista para Dirigentes
    
    # --- CORRECCIÓN AQUÍ: Usamos 'gestion/' para no chocar con 'admin/' ---
    path('gestion/jugadores/', views.admin_gestion_jugadores, name='admin_gestion_jugadores'), # Vista para Admin
    
    path('jugadores/editar/<int:jugador_id>/', views.editar_jugador, name='editar_jugador'),
    path('jugadores/eliminar/<int:jugador_id>/', views.eliminar_jugador, name='eliminar_jugador'),
    
    # API para Cédulas
    path('api/consultar-cedula/', views.api_consultar_cedula, name='api_consultar_cedula'),

    # ============================================
    # 3. GESTIÓN DE PARTIDOS (Calendario)
    # ============================================
    path('programar/', views.programar_partidos, name='programar_partidos'),
    path('partido/editar/<int:partido_id>/', views.editar_partido, name='editar_partido'),
    path('partido/eliminar/<int:partido_id>/', views.eliminar_partido, name='eliminar_partido'),
    path('partido/reiniciar/<int:partido_id>/', views.reiniciar_partido, name='reiniciar_partido'),

    # ============================================
    # 4. JUEGO Y VOCALÍA (El corazón del sistema)
    # ============================================
    path('partido/<int:partido_id>/resultado/', views.registrar_resultado, name='registrar_resultado'),
    path('partido/<int:partido_id>/vocalia/', views.gestionar_vocalia, name='gestionar_vocalia'),
    path('partido/<int:partido_id>/incidencia/', views.registrar_incidencia, name='registrar_incidencia'),
    
    # Acciones dentro de la Vocalía
    path('evento/eliminar/<int:evento_id>/', views.eliminar_evento, name='eliminar_evento'),
    path('multa/eliminar/<int:multa_id>/', views.eliminar_multa, name='eliminar_multa'),
    path('vocalia/asistencia/<int:partido_id>/<int:jugador_id>/', views.toggle_asistencia, name='toggle_asistencia'),
    
    # Acta Digital
    path('partido/acta-pdf/<int:partido_id>/', views.generar_acta_pdf, name='generar_acta_pdf'),

    # ============================================
    # 5. TABLAS DE POSICIONES Y ESTADÍSTICAS
    # ============================================
    path('tabla/<int:torneo_id>/', views.tabla_posiciones, name='tabla_posiciones'),
    
    path('generar-fase2/<int:torneo_id>/', views.generar_fase2, name='generar_fase2'),
    path('tabla/fase2/<int:torneo_id>/', views.tabla_posiciones_f2, name='tabla_posiciones_f2'),

    path('goleadores/<int:torneo_id>/', views.tabla_goleadores, name='tabla_goleadores'),
    path('reportes/', views.seleccionar_reporte, name='seleccionar_reporte'),
    path('reportes/<int:torneo_id>/', views.reporte_estadisticas, name='reporte_estadisticas'),

    # ============================================
    # 6. FINANZAS (DINERO)
    # ============================================
    path('finanzas/', views.gestionar_finanzas, name='gestionar_finanzas'),
    path('finanzas/pagar/', views.registrar_pago, name='registrar_pago'),
    path('finanzas/historial/<int:equipo_id>/', views.historial_pagos_equipo, name='historial_pagos_equipo'),
    path('finanzas/recibo/<int:pago_id>/', views.generar_recibo_pago_pdf, name='generar_recibo_pago_pdf'),
    path('sancion/cobrar/<int:sancion_id>/', views.cobrar_sancion, name='cobrar_sancion'),

    # ============================================
    # 7. SISTEMA DE RESERVAS (AMAZON STYLE)
    # ============================================
    path('reservar/', views.reservar_cancha, name='reservar_cancha'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),

    # FLUJO DE INSCRIPCIÓN
    path('torneos-disponibles/', views.ver_torneos_activos, name='ver_torneos_activos'),
    path('inscribirse/<int:torneo_id>/', views.solicitar_inscripcion, name='solicitar_inscripcion'),
    
    # ADMIN: APROBACIONES
    path('solicitudes/', views.gestionar_solicitudes, name='gestionar_solicitudes'),

    # CARRITO Y PAGOS
    path('carrito/', views.ver_carrito, name='ver_carrito'),
    path('checkout/', views.checkout_pago, name='checkout_pago'),

    # CANCELACIONES
    path('cancelar/reserva/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    path('cancelar/equipo/<int:equipo_id>/', views.cancelar_inscripcion_equipo, name='cancelar_inscripcion_equipo'),

    path('aprobar-reserva/<int:reserva_id>/', views.aprobar_reserva_admin, name='aprobar_reserva_admin'),

    path('torneo/<int:torneo_id>/generar-fixture/', views.generar_fixture, name='generar_fixture'),
    path('torneos/', views.gestionar_torneos, name='gestionar_torneos'),
    path('torneos/editar/<int:torneo_id>/', views.editar_torneo, name='editar_torneo'),

    path('horarios/', views.gestionar_horarios, name='gestionar_horarios'),
    path('horarios/eliminar/<int:horario_id>/', views.eliminar_horario, name='eliminar_horario'),

    path('marketing/', views.gestionar_medios, name='gestionar_medios'),
    path('marketing/foto/eliminar/<int:foto_id>/', views.eliminar_foto, name='eliminar_foto'),
    path('marketing/publicidad/eliminar/<int:pub_id>/', views.eliminar_publicidad, name='eliminar_publicidad'),
    
    path('recuperar/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('recuperar/completo/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    path('partido/<int:partido_id>/eliminar-evento-ultimo/<int:jugador_id>/<str:tipo>/', views.eliminar_evento_ultimo, name='eliminar_evento_ultimo'),

    path('torneo/<int:torneo_id>/generar-fase-2/', views.generar_fase2, name='generar_fase2'),
    path('torneo/<int:torneo_id>/proxima-fecha/', views.proxima_jornada, name='proxima_jornada'),
    path('torneo/<int:torneo_id>/generar-cuartos/', views.generar_cuartos_final, name='generar_cuartos_final'),

    path('torneo/<int:torneo_id>/generar-semis/', views.generar_semifinales, name='generar_semifinales'),
    path('torneo/<int:torneo_id>/generar-final/', views.generar_finales, name='generar_finales'),
    path('torneo/<int:torneo_id>/llaves-finales/', views.llaves_eliminatorias, name='llaves_eliminatorias'),

    path('torneos/eliminar/<int:torneo_id>/', views.eliminar_torneo, name='eliminar_torneo'),
    path('torneo/<int:torneo_id>/revertir-fase2/', views.revertir_fase2, name='revertir_fase2'),
    path('torneo/<int:torneo_id>/fixture-fase2/', views.generar_fixture_fase2, name='generar_fixture_fase2'),
]