import osimport timefrom functools import wrapsfrom django.db import transactionfrom core.http.response import HttpResponsefrom utils.log import loggerfrom utils.exceptions import PubErrorCustom,InnerErrorCustomfrom core.paginator import Paginationfrom django.template import loaderfrom django.core.serializers.json import DjangoJSONEncoderfrom data import dictlistfrom apps.user.models import Usersimport jsonfrom django.http import StreamingHttpResponsefrom libs.utils.redlock import ReadLockfrom apps.utils import url_joinfrom cryptokit import AESCryptofrom apps.public.utils import CheckIpForLoginimport base64def encrypt(word,key='LXJMTZCVFKQZNQ2J'):    crypto = AESCrypto(key,key)    data = crypto.encrypt(word,mode='cbc')    return base64.b64encode(data)def decrypt(word,key='LXJMTZCVFKQZNQ2J'):    try:        word=word.encode('utf-8')        crypto = AESCrypto(key,key)        data=base64.b64decode(word)        return crypto.decrypt(data)    except Exception as  e :        print(str(e))        raise PubErrorCustom("请求格式有误!")class Core_connector:    def __init__(self,**kwargs):        self.transaction = kwargs.get('transaction',None)        self.pagination = kwargs.get('pagination',None)        self.serializer_class = kwargs.get('serializer_class',None)        self.model_class = kwargs.get('model_class',None)        self.lock = kwargs.get('lock',None)        self.encryption =  kwargs.get('encryption',False)        self.check_google_token = kwargs.get('check_google_token',None)        self.is_file = kwargs.get('is_file',None)        self.h5ValueHandler = None    def __request_validate(self,request,**kwargs):        if os.environ.get('DEPLOY_MODE', None) == 'pro' and hasattr(request,'user') and  hasattr(request.user,'userid') and request.user.userid!=1:            CheckIpForLogin(ip=request.META.get("HTTP_X_REAL_IP"), userid=request.user.userid).run()            # CheckIpForLogin(ip="49.144.195.119", userid=request.user.userid).run()        logger.info("请求API:{}".format(request.path))        logger.info("用户ID{}".format(request.user.userid if hasattr(request,'user') and hasattr(request.user,'userid') else 0))        if request.META.get('HTTP_ENCRYPTION') == 'encryption':            self.encryption = True        self.token = None        if self.check_google_token:            if request.META.get('HTTP_BUSINESSNOENCRYPTION') == '1':                self.encryption = False            else:                self.encryption = True            token = request.META.get('HTTP_TOKEN')            if not token:                raise PubErrorCustom("无效的用户!")            userid = token.split(',')[0]            try :                request.user = Users.objects.get(userid=userid)                self.token = request.user.google_token            except Users.DoesNotExist:                raise PubErrorCustom("无效的用户!")        else:            self.token = "LXJMTZCVFKQZNQ2J"        if request.method == 'GET':            if 'data' not in request.query_params:                raise PubErrorCustom("请求报文有误!")            if self.encryption:                if request.query_params.get('data') and len(                        request.query_params.get('data')) and request.query_params.get('data') != '{}':                    request.query_params_format = json.loads(decrypt(request.query_params.get('data'), self.token))                else:                    request.query_params_format = {}            else:                request.query_params_format = json.loads(request.query_params.get('data')) \                    if request.query_params.get('data') and len(request.query_params.get('data')) > 0 else {}            logger.info("请求数据:{}".format(request.query_params_format))        if request.method == 'POST' :            if 'data' not in request.data:                raise PubErrorCustom("请求报文有误!")            if self.encryption:                if request.data.get('data') and len(request.data.get('data')):                    request.data_format = json.loads(decrypt(request.data.get('data'),self.token))                else:                    request.data_format = {}            else:                request.data_format = request.data.get('data') if request.data.get('data') and len(request.data.get('data')) > 0 else {}            logger.info("请求数据:{}".format(request.data_format))        if not self.serializer_class:            return kwargs        pk = kwargs.get('pk')        instance = None        if pk:            try:                instance = self.model_class.objects.get(pk=pk)            except TypeError:                raise PubErrorCustom('serializer_class类型错误')            except Exception:                raise PubErrorCustom('未找到')        serializer = self.serializer_class(data=request.data_format, instance=instance)        if not serializer.is_valid():            errors = [key + ':' + value[0] for key, value in serializer.errors.items() if isinstance(value, list)]            if errors:                error = errors[0]                error = error.lstrip(':').split(':')                try:                    error = "{}:{}".format( getattr(dictlist ,error[0]) , error[1])                except AttributeError as e:                    error = error[1]            else:                for key, value in serializer.errors.items():                    if isinstance(value, dict):                        key, value = value.popitem()                        error = key + ':' + value[0]                        break            raise PubErrorCustom(error)        kwargs.setdefault('serializer',serializer)        kwargs.setdefault('instance', instance)        return kwargs    def __run(self,func,outside_self,request,*args, **kwargs):        if self.lock:            resource = eval(self.lock.get('resource')) if isinstance(self.lock,dict) and self.lock.get('resource') else \                    "[%s%s]"%(outside_self.__class__.__name__, getattr(func, '__name__'))            with ReadLock(resource=resource) as Lock:                if not Lock:                    if isinstance(self.lock,dict) and "msg" in self.lock:                        raise PubErrorCustom(self.lock.get("msg"))                    else:                        raise PubErrorCustom("正在进行处理,请稍等!")                else:                    if self.transaction:                        with transaction.atomic():                            res = func(outside_self, request, *args, **kwargs)                    else:                        res = func(outside_self, request, *args, **kwargs)        else:            if self.transaction:                with transaction.atomic():                    res = func(outside_self, request, *args, **kwargs)            else:                res = func(outside_self, request, *args, **kwargs)        if not self.is_file :            if res and 'data' in res and \                ((self.pagination and isinstance(res['data'],list)) or (self.pagination and isinstance(res['data'],dict) and 'data' in res['data'])):                if 'header' in res:                    header=res['header']                    res=Pagination().get_paginated(data=res['data'],request=request)                    res['header']={**res['header'],**header}                else:                    res = Pagination().get_paginated(data=res['data'],request=request)            if res and 'data' in res and 'res' in res['data'] and res['data']['res'] and 'htmlfile' in res['data'] and  res['data']['htmlfile']:                html = loader.render_to_string(res['data']['htmlfile'], {                    'data': res['data']['res']                }, request, using=None)                with open('/var/html/tianyi/{}.html'.format(res['data']['ordercode']), 'w') as f1:                    f1.write(html)                data = {"path": url_join('/tianyi/{}.html').format(res['data']['ordercode'])}                if self.encryption:                    data = encrypt(json.dumps(data, cls=DjangoJSONEncoder), self.token)                return HttpResponse(data=data, headers=None, msg='操作成功!')            if not isinstance(res, dict):                res = {'data': None, 'msg': None, 'header': None}            if 'data' not in res:                res['data'] = None            if 'msg' not in res:                res['msg'] =  {}            if 'header' not in res:                res['header'] = None            logger.info("返回报文:{}".format(res['data']))            if self.encryption:                res['data'] = encrypt(json.dumps(res['data'], cls=DjangoJSONEncoder), self.token)            else:                res['data'] = res['data']            # if res['header']:            #     res['header']['version'] = os.environ.get('VERSION', '1.0.1')            # else:            #     res['header'] = {}            #     res['header']['version'] = os.environ.get('VERSION', '1.0.1')            return HttpResponse(data= res['data'],headers=res['header'], msg=res['msg'])        else:            def file_iterator(file_name, chunk_size=512):                with open(file_name, 'rb') as f:                    while True:                        c = f.read(chunk_size)                        if c:                            yield c                        else:                            break            response = StreamingHttpResponse(file_iterator(res))            response['Content-Type'] = 'application/octet-stream'            response['Content-Disposition'] = 'attachement;filename="{0}"'.format("qrcode.png")            return response    def __response__validate(self,outside_self,func,response):        logger.info('[%s : %s]Training complete in %lf real seconds' % (outside_self.__class__.__name__, getattr(func, '__name__'), self.end - self.start))        return response    def __call__(self,func):        @wraps(func)        def wrapper(outside_self,request,*args, **kwargs):            try:                self.start = time.time()                kwargs=self.__request_validate(request,**kwargs)                response=self.__run(func,outside_self,request,*args, **kwargs)                self.end=time.time()                return self.__response__validate(outside_self,func,response)            except PubErrorCustom as e:                logger.error('[%s : %s  ] : [%s]'%(outside_self.__class__.__name__, getattr(func, '__name__'),e.msg))                return HttpResponse(success=False, msg=e.msg, data=None)            except InnerErrorCustom as e:                logger.error('[%s : %s  ] : [%s]'%(outside_self.__class__.__name__, getattr(func, '__name__'),e.msg))                return HttpResponse(success=False, msg=e.msg, rescode=e.code, data=None)            except Exception as e:                logger.error('[%s : %s  ] : [%s]'%(outside_self.__class__.__name__, getattr(func, '__name__'),str(e)))                return HttpResponse(success=False, msg=str(e), data=None)        return wrapperclass Core_connector_exec:    def __init__(self,**kwargs):        self.transaction = kwargs.get('transaction',None)        self.pagination = kwargs.get('pagination',None)        self.serializer_class = kwargs.get('serializer_class',None)        self.model_class = kwargs.get('model_class',None)        self.lock = kwargs.get('lock',None)        self.is_file = kwargs.get('is_file',None)    def __request_validate(self,request,**kwargs):       return kwargs    def __run(self,func,outside_self,request,*args, **kwargs):        if self.lock:            resource = eval(self.lock.get('resource')) if isinstance(self.lock, dict) and self.lock.get('resource') else \                "[%s%s]" % (outside_self.__class__.__name__, getattr(func, '__name__'))            with ReadLock(resource=resource) as Lock:                if not Lock:                    if isinstance(self.lock, dict) and "msg" in self.lock:                        raise PubErrorCustom(self.lock.get("msg"))                    else:                        raise PubErrorCustom("正在进行处理,请稍等!")                else:                    if self.transaction:                        with transaction.atomic():                            res = func(outside_self, request, *args, **kwargs)                    else:                        res = func(outside_self, request, *args, **kwargs)        else:            if self.transaction:                with transaction.atomic():                    res = func(outside_self, request, *args, **kwargs)            else:                res = func(outside_self, request, *args, **kwargs)        if self.pagination and isinstance(res['data'],list):            if 'header' in res:                header=res['header']                res=Pagination().get_paginated(data=res['data'],request=request)                res['header']={**res['header'],**header}            else:                res = Pagination().get_paginated(data=res['data'],request=request)        if not isinstance(res, dict):            res = {'data': None, 'msg': None, 'header': None}        if 'data' not in res:            res['data'] = None        if 'msg' not in res:            res['msg'] =  {}        if 'header' not in res:            res['header'] = None        return HttpResponse(data= res['data'],headers=res['header'], msg=res['msg'])    def __response__validate(self,outside_self,func,response):        logger.debug('[%s : %s]Training complete in %lf real seconds' % (outside_self.__class__.__name__, getattr(func, '__name__'), self.end - self.start))        return response    def __call__(self,func):        @wraps(func)        def wrapper(outside_self,request,*args, **kwargs):            try:                self.start = time.time()                kwargs=self.__request_validate(request,**kwargs)                response=self.__run(func,outside_self,request,*args, **kwargs)                self.end=time.time()                return self.__response__validate(outside_self,func,response)            except PubErrorCustom as e:                return HttpResponse(success=False, msg=e.msg, data=None)            except Exception as e:                logger.error('[%s : %s  ] : [%s]'%(outside_self.__class__.__name__, getattr(func, '__name__'),str(e)))                return HttpResponse(success=False, msg=str(e), data=None)        return wrapper