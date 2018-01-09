import json
import types
import threading

def unpack(num, seq,defval=None):
    ln = len(seq)
    if ln > num:
        return seq[0:num]
    if ln < num:
        return seq+[defval]*(num-ln)
    return seq
class ITMP:
    def __init__(self):
        #super()
        self.links = {}

        self.msgid = 0

        self.transactions = {}
        self.transactionsLock = threading.Lock()
        self.subscriptions = {}

        self.pollsubs = {}
        self.urls = {}
        self.started = False

        self.addCall('transactions', self.calltransactions)

        self.addCall('subscriptions', self.callsubscriptions)

    def calltransactions(self, args):
        """list all current transactions"""
        ret = []
        self.transactionsLock.acquire()
        for trid in self.transactions:
            tr = self.transactions.get(trid)
            ret.append({'id':trid, 'itmp':tr.msg[0], 'third':tr.msg[2], 'args':args})
        self.transactionsLock.release()
        return ret

    def start(self):
        """start all links"""
        for linkname in self.links:
            self.links[linkname].start(self)
        self.started = True
        return True
    
    def callsubscriptions(self, args):
        """subscriptions call"""
        ret = {'args':args}
        for sb in self.subscriptions:
            ret[sb] = self.subscriptions[sb]
        for sb in self.pollsubs:
            ret[sb] = self.pollsubs[sb]
        return ret


    def addLink(self, lnk):
        """add link to itmp core"""
        linkname = lnk.lnkname
        self.links[linkname] = lnk

    def deleteConnection(self, name):
        """delete connection """
        link = self.links[name]
        del self.links[name]
        link.stop()


    def doneTransaction(self, key, result, props=None):
        """ finish transaction, delete from transaction list and store transeaction result"""
        self.transactionsLock.acquire()
        t = self.transactions.get(key)
        if t:
            wait = t['wait']
            if wait:
                with wait:
                    t['result'] = result
                    t['properties'] = props
                    del self.transactions[key]
                    wait.notify_all()
        else:
            print('unexpected result', key, result)# msg)
        self.transactionsLock.release()
        return t

    def processConnect(self, key, payload):
        """process connect message"""
        #self.processConnect()
        t = self.transactions.get(key)
        if t:
            #clearTimeout(t.timeout)
            del self.transactions[key]
            [code, message] = payload
            if t.err:
                t.err(code, message)
            else:
                print('unexpected error', payload)

    def processError(self, key, payload):
        """process error message"""
        self.transactionsLock.acquire()
        t = self.transactions.get(key)
        if t:
            [code, message] = unpack(2, payload)
            wait = t['wait']
            if wait:
                with wait:
                    t['result'] = (code, message)
                    del self.transactions[key]
                    wait.notify_all()
        self.transactionsLock.release()

    def processCall(self, addr, mid, payload):
        """ process call message"""
        [uri, args, opts] = unpack(3, payload)
        if uri == "":
            ret = {}
            for lnk in self.urls:
                ret[lnk] = ': function'
            for lnk in self.links:
                ret[lnk] = '*'
            self.answer(addr, [9, mid, ret])
        else:
            f = self.urls.get(uri)
            if f and ('call' in f or hasattr(f, 'call')):
                ret = f['call'](args, opts)
                self.answer(addr, [9, mid, ret])
            else:
                [link, subaddr, suburi] = self.getLink(uri)
                if link:
                    if link.call:
                        self.answer(addr, [9, mid, link.call(subaddr, suburi)])
                    #else:
                        #self.transactionLink(link, subaddr, [8, 0, suburi, args, opts], lambda answerdata: self.answer(addr, [9, id, answerdata], None), lambda errcode, errmsg: self.answer(addr, [5, id, errcode, errmsg], None))
                else:
                    #print(f"unexpected call{json.dumps(payload)}")
                    self.answer(addr, [5, mid, 404, 'no such uri'])

    def processResult(self, key, payload):
        [result, properties] = unpack(2, payload)
        self.doneTransaction(key, result, properties)

    def processEvent(self, addr, payload):
        # print("subscribed",msg)
        [topic, args, ots] = unpack(3,payload)
        used = False
        subskey = f"{addr}/{topic}"
        subskeyParts = subskey.split('/')
        subspath = subskeyParts[0]
        for k in subskeyParts:
            t = self.subscriptions.get(f"{subspath}/*")
            if t:
                t.done(topic, args, ots)
                used = True
                subspath = f"{subspath}/{subskeyParts[k]}"
            t = self.subscriptions.get(subskey)
            if t:
                used = True
                t.done(topic, args, ots)
            elif not used:
                print('unexpected result', payload)
            #if not used:
            #    self.emit('event', addr, topic, args, ots)

    def processSubscribe(self, addr, id, payload):
        # print("subscribу",msg)
        [uri, opts] = payload
        f = self.urls.get(uri)
        if f and f.subscribe:
            s = {'addr':addr}
            ret = f.subscribe(uri, opts, s)
            self.answer(addr, [17, id, ret])
            self.pollsubs[uri] = s
        else:
            [link, subaddr, suburi] = self.getLink(uri) #suburi = ''
            if link:
                if link.subscribe:
                    link.subscribe(subaddr, suburi, opts, lambda answerdata: self.answer(addr, [17, id, answerdata]), lambda errcode, errmsg: self.answer(addr, [5, id, errcode, errmsg]))
                    self.pollsubs[f"{link.lnkname}/{subaddr}/{suburi}"] = { 'addr':addr }
                else:
                    print(f"unexpected subs{json.dumps(payload)}")
                    self.answer(addr, [5, id, 404, 'no such uri'])

    def processDescribe(self, addr, id, payload):
        [uri, args, opts] = unpack(3,payload)
        if uri == '':
            self.answer(addr, [7, id, 'js root'])
        else:
            f = self.urls.get(uri)
            if f:
                ret = f.desription
                self.answer(addr, [7, id, ret])
            else:
                [link, subaddr, suburi] = self.getLink(uri)
                if link:
                    self.transactionLink(link, subaddr, [6, 0, suburi, args, opts], lambda answerdata: self.answer(addr, [7, id, answerdata]),lambda errcode, errmsg: self.answer(addr, [5, id, errcode, errmsg]))
                else:
                    print(f"unexpected descr{json.dumps(payload)}")
                    self.answer(addr, [5, id, 404, 'no such uri'])

    def processSubscribed(self, addr, key, id, payload):
        t = self.doneTransaction(key, None)
        if t:
            self.subscriptions[f"{addr}/{t.msg[2]}"] = {'err': t.err, 'done': t.done}
        else:
            print('unexpected result', payload)

    def processUnsubscribed(self, addr, key, id, payload):
        [id, opts] = unpack(2, payload)
        t = self.doneTransaction(key, None, opts)
        if t:
            del self.subscriptions[f"{addr}/{t.msg[2]}"]
        else:
            print('unexpected result', payload)

    def process(self, addr, msg):
        if isinstance(msg,list) and len(msg) >= 1 and type(msg[0]) == int:
            command, *payload = msg
            #command = msg[0]
            #payload = msg[1:]
            #let key
            #let id
            if len(msg) >= 1 and type(msg[1]) == int:
                id = payload[0]
                payload = payload[1:]
                key = f"{addr}:{id}"
            else:
                key = f"{addr}:"
                id = ''

            if command == 0: # [CONNECT, Connection:id, Realm:uri, Details:dict] open connection
                self.processConnect(key, payload)
            elif command == 1: # [CONNECTED, CONNECT.Connection:id, Session:id, Details:dict] confirm connection
                print("")
            elif command == 2: # [ABORT, Code:integer, Reason:string, Details:dict] terminate connection
                print("")
            elif command == 4: # [DISCONNECT, Code:integer, Reason:string, Details:dict] clear finish connection
                print("")
            elif command == 5: # [ERROR, Request:id, Code:integer, Reason:string, Details:dict] error notificarion
                self.processError(key, payload)
            elif command == 6: # [DESCRIBE, Request:id, Topic:uri, Options:dict] get description
                self.processDescribe(addr, id, payload)
            elif command == 7: # [DESCRIPTION, DESCRIBE.Request:id, description:list, Options:dict] response
                [result, properties] = unpack(2,payload)
                self.doneTransaction(key, result, properties)
            # RPC
            elif command == 8: # [CALL, Request:id, Procedure:uri, Arguments, Options:dict] call
                self.processCall(addr, id, payload)
            elif command == 9: # [RESULT, CALL.Request:id, Result, Details:dict] call response
                self.processResult(key, payload)
            # RPC Extended
            elif command == 10: # [ARGUMENTS, CALL.Request:id,ARGUMENTS.Sequuence:integer,Arguments,Options:dict]
                #  additional arguments for call
                print("")
            elif command == 11: # [PROGRESS, CALL.Request:id, PROGRESS.Sequuence:integer, Result, Details:dict]
                #  call in progress
                print("")
            elif command == 12: # [CANCEL, CALL.Request:id, Details:dict] call cancel
                # publish
                print("")
            elif command == 13: # [EVENT, Request:id, Topic:uri, Arguments, Options:dict] event
                self.processEvent(addr, payload)
            elif command == 14: # [PUBLISH, Request:id, Topic:uri, Arguments, Options:dict] event with acknowledge
                print('publish', msg)
            elif command == 15: # [PUBLISHED, PUBLISH.Request:id, Publication:id, Options:dict] event acknowledged
                print('published', msg)
            # subscribe	
            elif command == 16: # [SUBSCRIBE, Request:id, Topic:uri, Options:dict] subscribe
                self.processSubscribe(addr, id, payload)
            elif command == 17: # [SUBSCRIBED, SUBSCRIBE.Request:id, Options:dict] subscription confirmed
                self.processSubscribed(addr, key, id, payload)
            elif command == 18: # [UNSUBSCRIBE, Request:id, Topic:uri, Options:dict]
                print('unsubscribe', msg)
            elif command == 20: # [UNSUBSCRIBED, UNSUBSCRIBE.Request:id, Options:dict]
                self.processUnsubscribed(addr, key, id, payload)
            # keep alive
            elif command == 33: # [KEEP_ALIVE, Request:id, Options:dict] keep alive request
                print("")
            elif command == 34: # [KEEP_ALIVE_RESP, KEEP_ALIVE.Request:id, Options:dict] keep alive responce
                print("")
            else:
                print('wrong message ', msg)

    def answer(self, addr, msg):
        """send answer to return address"""
        [linkname, subaddr] = unpack(2, addr.split('/', 1))
        link = self.links.get(linkname)
        if link:
            link.send(subaddr, msg)

    def getLink(self, addr):
        """get link by link address prefix"""
        [linkname, subaddr, uri] = unpack(3, addr.split('/', 2))
        link = self.links.get(linkname)
        if not link or not link.addressable:
            if uri:
                return [link, None, f"{subaddr}/{uri}"]
            return [link, None, subaddr]
        return [link, subaddr, uri]

    def transaction(self, addr, msg):
        """do transaction send request and wait for responce"""
        [linkname, subaddr] = unpack(2, addr.split('/', 1))
        link = self.links.get(linkname)
        return self.transactionLink(link, subaddr, msg)

    def sendfail(self, addr, key, result):
        """ finish transaction, delete from transaction list and store transeaction result"""
        self.transactionsLock.acquire()
        t = self.transactions.get(key)
        if t:
            wait = t['wait']
            if wait:
                with wait:
                    t['result'] = result
                    del self.transactions[key]
                    wait.notify_all()
        else:
            print('unexpected result', key, result)# msg)
        self.transactionsLock.release()
        return t


    def transactionLink(self, link, subaddr, msg):
        if type(msg[1]) == int:
            msg[1] = self.msgid
            self.msgid += 1

        key = f"{link.lnkname}/{subaddr}:{msg[1] if type(msg[1]) == int else ''}"
        wait = threading.Condition()
        tr = {'msg':msg, 'wait':wait}
        self.transactions[key] = tr
        err = link.send(subaddr, msg, key)
        if err:
            tr['result'] = (500, 'send error')
        else:
            with wait:
                if not 'result' in tr:
                    ok = wait.wait(0.500)
                    if ok: return tr['result']
        if key in self.transactions:
            del self.transactions[key]
        return tr.get('result')

    def emitEvent(self, topic, msg):
        to = self.pollsubs.get(topic)
        if to:
            [link, subaddr, uri] = self.getLink(to.addr)
        #if (typeof link !== 'object')
        #return
        id = self.msgid
        self.msgid += 1

        link.send(subaddr, [13, id, topic, msg])

    def call(self, addr, name, param):
        msg = [8, 0, name, param]
        return self.transaction(addr, msg)

    def connect(self, addr, name, param):
        msg = [0, 0, name, [param]]
        return self.transaction(addr, msg)

    def describe(self, addr, name):
        msg = [6, 0, name]
        return self.transaction(addr, msg)

    def subscribe(self, addr, url, param):
        msg = [16, 0, url, param]
        return self.transaction(addr, msg)

    def unsubscribe(self, addr, url, param):
        subskey = f"{addr}/{url}"
        t = self.subscriptions.get(subskey)
        if t:
            self.subscriptions.delete(subskey)
            msg = [18, 0, url, param]
            return self.transaction(addr, msg)
        err(404, 'subscription not found')

    def addCall(self, name, func):
        self.urls[name] = {'call': func}

    def addSubscribe(self, name, func):
        self.urls[name] = {'subscribe': func}

    def queueSize(self, addr):
        subaddr = ''
        linkname = ''
        if type(addr) == str:
            [subaddr, linkname] = unpack(2, addr.split('/', 1), '')
        link = self.links.get(linkname)
        if type(link) != type:
            return -1

        return link.queueSize(subaddr)
