from anthill.framework.handlers import RequestHandler, TemplateHandler
from anthill.framework.http.errors import HttpBadRequestError
from anthill.framework.utils.decorators import authenticated
from anthill.framework.utils.translation import translate as _
from anthill.framework.utils import timezone
from anthill.framework.utils.asynchronous import thread_pool_exec as future_exec
from anthill.platform.handlers.jsonrpc import JsonRPCSessionHandler, jsonrpc_method
from anthill.platform.auth.handlers import (
    LoginHandler as BaseLoginHandler,
    LogoutHandler as BaseLogoutHandler,
)
from anthill.platform.handlers.base import InternalRequestHandlerMixin, UserHandlerMixin
from anthill.platform.api.internal import connector, InternalAPIError
from ._base import ServiceContextMixin, UserTemplateServiceRequestHandler, PageHandlerMixin
from admin.ui.modules import ServiceCard
from admin.models import UpdateLog
from typing import Optional
import logging
import inspect
import functools

logger = logging.getLogger('anthill.application')


# @authenticated()
class HomeHandler(InternalRequestHandlerMixin, PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'index'

    async def get_service_cards(self):
        metadata = self.settings['services_meta']
        service_cards = sorted(map(lambda m: ServiceCard.Entry(**m), metadata))
        return service_cards

    async def get_context_data(self, **kwargs):
        service_cards = await self.get_service_cards()
        kwargs.update(service_cards=service_cards)
        context = await super().get_context_data(**kwargs)
        return context


class LoginHandler(PageHandlerMixin, BaseLoginHandler):
    page_name = 'login'


# @authenticated()
class LogoutHandler(BaseLogoutHandler):
    handler_name = 'login'  # Redirect to


# @authenticated()
class DebugHandler(PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'debug'

    async def get_context_data(self, **kwargs):
        context = await super().get_context_data(**kwargs)
        return context


class DebugSessionHandler(PageHandlerMixin, JsonRPCSessionHandler, UserHandlerMixin):
    """Defines json-rpc methods for debugging."""
    page_name = 'debug-session'

    def __init__(self, application, request, dispatcher=None, **kwargs):
        super().__init__(application, request, dispatcher, **kwargs)
        self._context = {'service': None}  # used by context-based methods

    def _set_context(self, name: str, value: Optional[str]):
        if name in self._context:
            self._context[name] = value

    @jsonrpc_method()
    def help(self):
        """Shows supported commands."""
        res = ''
        for i, f in enumerate(self.dispatcher.values(), 1):
            if f.kwargs.get('system', False):
                continue
            anno = inspect.getfullargspec(f).annotations
            res += '%s) %s (%s) => %s\n' % (
                i, f.__name__, str(anno).strip('{}'), f.__doc__)
        return res.rstrip()

    @jsonrpc_method()
    def get_context(self, name: str = ''):
        """Get context variables."""
        if name in self._context:
            return 'Current context %s: %s' % (name, self._context[name] or '--')
        else:
            return 'No such context, (%s) available.' % ', '.join(self._context.keys())

    @jsonrpc_method()
    def set_context(self, name: str, value: Optional[str]):
        """Set context variable."""
        self._set_context(name, value)

    @jsonrpc_method()
    def clear_context(self, name: str):
        """Clear context variable."""
        self._set_context(name, None)


def _util_internal_wrapper(on_error=None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                await func(*args, **kwargs)
                return {'message': args[0].SUCCESSFUL_MESSAGE}
            except InternalAPIError as e:
                if callable(on_error):
                    await on_error(e)
                return e.args[0]
        return wrapper
    return decorator


class UtilsSessionHandler(JsonRPCSessionHandler, UserHandlerMixin):
    SUCCESSFUL_MESSAGE = _('Completed successfully.')

    @jsonrpc_method()
    @_util_internal_wrapper()
    async def update(self, service_name, version=None):
        await connector.internal_request(service_name, 'update', version=version)
        log_kwargs = {
            'finished': timezone.now(),
            'service_name': service_name,
            'author_id': self.current_user.id,
            'to_version': version,
            'from_version': self.application.version,
            'last_failure_tb': None
        }
        # TODO: create UpdateLog entry
        # await future_exec(UpdateLog.create, **log_kwargs)

    @jsonrpc_method()
    @_util_internal_wrapper()
    async def reload(self, service_name):
        await connector.internal_request(service_name, 'reload')


# @authenticated()
class SidebarMainToggle(RequestHandler, UserHandlerMixin):
    """Save main sidebar state expanded or closed."""

    async def get(self):
        if self.is_ajax():
            expanded = self.session.get('sidebar-main-expanded', True)
            self.session['sidebar-main-expanded'] = not expanded
        else:
            raise HttpBadRequestError

    async def post(self):
        await self.get()


# @authenticated()
class LogRequestHandler(ServiceContextMixin, PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'log'
    service_name = None

    def initialize(self, service_name=None):
        if service_name is not None:
            self.service_name = service_name

    async def get_context_data(self, **kwargs):
        context = await super().get_context_data(**kwargs)
        context['has_detached_right'] = True
        return context


# @authenticated()
class SettingsRequestHandler(PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'settings'


# @authenticated()
class AuditLogRequestHandler(PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'audit_log'


# @authenticated()
class ProfileRequestHandler(PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'profile'


# @authenticated()
class UpdateManagerRequestHandler(PageHandlerMixin, TemplateHandler, UserHandlerMixin):
    page_name = 'update_manager'

    async def get_context_data(self, **kwargs):
        context = await super().get_context_data(**kwargs)
        context['services_list'] = self.settings['services_all_meta']
        return context
